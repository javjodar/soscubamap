from flask import jsonify, request, make_response, session, current_app
import math
import json
import os
import secrets
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from flask_login import current_user
import requests

from app.extensions import db, limiter
from app.services.input_safety import has_malicious_input
from app.services.recaptcha import verify_recaptcha, recaptcha_enabled
from app.services.text_sanitize import sanitize_text
from app.models.comment import Comment
from app.models.user import User
from app.models.role import Role
from app.models.media import Media
from app.models.post_revision import PostRevision
from app.models.post_edit_request import PostEditRequest
from app.models.site_setting import SiteSetting
from app.services.media_upload import (
    validate_files,
    upload_files,
    media_json_from_post,
    get_media_payload,
)
from app.models.chat_message import ChatMessage
from app.models.chat_presence import ChatPresence
from app.models.discussion_post import DiscussionPost
from app.models.discussion_comment import DiscussionComment
from app.models.push_subscription import PushSubscription
from app.models.vote_record import VoteRecord
from app.services.vote_identity import get_voter_hash
from app.models.connectivity_snapshot import ConnectivitySnapshot
from app.models.connectivity_ingestion_run import ConnectivityIngestionRun
from app.models.connectivity_province_status import ConnectivityProvinceStatus
from app.services.connectivity import (
    STATUS_CRITICAL,
    STATUS_COLORS,
    STATUS_LABELS,
    STATUS_UNKNOWN,
    extract_series_points,
    get_latest_hourly_point,
    score_to_status,
    serialize_snapshot_time,
    to_float,
)
from app.services.connectivity_geo import (
    diagnose_province_geojson,
    enrich_geojson_with_status,
    load_province_geojson,
    province_names_from_geojson,
)
from app.services.geo_lookup import list_provinces
from app.services.cuba_locations import PROVINCES

from app.models.post import Post
from sqlalchemy.orm import selectinload
from app.models.category import Category
from sqlalchemy import func
from . import api_bp


def _is_admin_user():
    return current_user.is_authenticated and current_user.has_role("administrador")


def _get_chat_nick():
    nick = session.get("chat_nick")
    if nick and (nick.lower() != "admin" or _is_admin_user()):
        return nick
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    code = "".join(secrets.choice(alphabet) for _ in range(6))
    nick = f"Anon-{code}"
    session["chat_nick"] = nick
    return nick


def _sanitize_nick(nickname: str, fallback: str) -> str:
    value = (nickname or "").strip()
    if not value:
        return fallback
    if value.lower() == "admin" and not _is_admin_user():
        return fallback
    return value[:80]


def _push_enabled() -> bool:
    return bool(
        current_app.config.get("VAPID_PUBLIC_KEY")
        and current_app.config.get("VAPID_PRIVATE_KEY")
    )


def _truthy_param(raw):
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _mask_secret(value):
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 10:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _cf_api_token():
    return (current_app.config.get("CF_API_TOKEN") or os.getenv("CF_API_TOKEN") or "").strip()


def _connectivity_payload_summary(payload):
    if not isinstance(payload, dict):
        return {
            "parse_ok": False,
            "main_points": 0,
            "previous_points": 0,
            "latest_main": None,
            "latest_previous": None,
            "latest_main_hourly": None,
        }

    main_points = extract_series_points(payload, "main")
    previous_points = extract_series_points(payload, "previous")
    latest_main = main_points[-1] if main_points else None
    latest_previous = previous_points[-1] if previous_points else None
    latest_main_hourly = get_latest_hourly_point(payload, "main")

    def _serialize_point(point):
        if not point:
            return None
        return {
            "timestamp_utc": serialize_snapshot_time(point.get("timestamp")),
            "value": point.get("value"),
        }

    return {
        "parse_ok": True,
        "main_points": len(main_points),
        "previous_points": len(previous_points),
        "latest_main": _serialize_point(latest_main),
        "latest_previous": _serialize_point(latest_previous),
        "latest_main_hourly": _serialize_point(latest_main_hourly),
    }


def _serialize_timeseries_point(point):
    if not point:
        return None
    return {
        "timestamp_utc": serialize_snapshot_time(point.get("timestamp")),
        "value": to_float(point.get("value")),
    }


def _latest_successful_connectivity_run():
    return (
        ConnectivityIngestionRun.query.filter(
            ConnectivityIngestionRun.status == "success",
            ConnectivityIngestionRun.payload_json.isnot(None),
            ConnectivityIngestionRun.payload_json != "",
        )
        .order_by(
            ConnectivityIngestionRun.started_at_utc.desc(),
            ConnectivityIngestionRun.id.desc(),
        )
        .first()
    )


def _build_http_requests_24h_summary():
    run = _latest_successful_connectivity_run()
    if not run or not run.payload_json:
        return {
            "available": False,
            "reason": "No hay ingestas exitosas con payload.",
            "series_main": [],
            "series_previous_aligned": [],
        }

    try:
        payload = json.loads(run.payload_json)
    except Exception as exc:
        return {
            "available": False,
            "reason": f"Payload de ingesta invalido: {exc}",
            "source_run_id": run.id,
            "source_started_at_utc": serialize_snapshot_time(run.started_at_utc),
            "source_finished_at_utc": serialize_snapshot_time(run.finished_at_utc),
            "series_main": [],
            "series_previous_aligned": [],
        }

    main_points_all = extract_series_points(payload, "main")
    previous_points_all = extract_series_points(payload, "previous")
    if not main_points_all:
        return {
            "available": False,
            "reason": "La serie main no contiene puntos.",
            "source_run_id": run.id,
            "source_started_at_utc": serialize_snapshot_time(run.started_at_utc),
            "source_finished_at_utc": serialize_snapshot_time(run.finished_at_utc),
            "series_main": [],
            "series_previous_aligned": [],
        }

    latest_ts = main_points_all[-1].get("timestamp")
    window_start = latest_ts - timedelta(hours=24) if latest_ts else None
    main_points = [
        item
        for item in main_points_all
        if item.get("timestamp") is not None and (window_start is None or item.get("timestamp") >= window_start)
    ]
    if not main_points:
        main_points = main_points_all[-24:]

    previous_aligned = []
    if previous_points_all and main_points:
        align_count = min(len(previous_points_all), len(main_points))
        prev_tail = previous_points_all[-align_count:]
        main_tail = main_points[-align_count:]
        for main_item, prev_item in zip(main_tail, prev_tail):
            previous_aligned.append(
                {
                    "timestamp": main_item.get("timestamp"),
                    "value": to_float(prev_item.get("value")),
                }
            )

    main_values = [to_float(item.get("value")) for item in main_points]
    main_values = [value for value in main_values if value is not None]

    latest_main_value = to_float(main_points[-1].get("value")) if main_points else None
    latest_previous_value = (
        to_float(previous_aligned[-1].get("value")) if previous_aligned else None
    )

    delta_pct = None
    if (
        latest_main_value is not None
        and latest_previous_value is not None
        and latest_previous_value > 0
    ):
        delta_pct = ((latest_main_value - latest_previous_value) / latest_previous_value) * 100.0

    peak_main_value = max(main_values) if main_values else None
    min_main_value = min(main_values) if main_values else None
    avg_main_value = (sum(main_values) / len(main_values)) if main_values else None

    max_drop_from_peak_pct = None
    if (
        peak_main_value is not None
        and min_main_value is not None
        and peak_main_value > 0
    ):
        max_drop_from_peak_pct = ((peak_main_value - min_main_value) / peak_main_value) * 100.0

    return {
        "available": bool(main_points),
        "source_run_id": run.id,
        "source_started_at_utc": serialize_snapshot_time(run.started_at_utc),
        "source_finished_at_utc": serialize_snapshot_time(run.finished_at_utc),
        "latest_timestamp_utc": serialize_snapshot_time(main_points[-1].get("timestamp")) if main_points else None,
        "latest_main_value": latest_main_value,
        "latest_previous_value": latest_previous_value,
        "delta_pct": delta_pct,
        "peak_main_value": peak_main_value,
        "min_main_value": min_main_value,
        "avg_main_value": avg_main_value,
        "max_drop_from_peak_pct": max_drop_from_peak_pct,
        "series_main": [
            point for point in (_serialize_timeseries_point(item) for item in main_points) if point
        ],
        "series_previous_aligned": [
            point
            for point in (_serialize_timeseries_point(item) for item in previous_aligned)
            if point
        ],
    }


def _cloudflare_probe():
    api_url = (current_app.config.get("CLOUDFLARE_RADAR_HTTP_TIMESERIES_URL") or "").strip()
    timeout_seconds = int(current_app.config.get("CONNECTIVITY_FETCH_TIMEOUT_SECONDS", 30))
    token = _cf_api_token()

    result = {
        "requested_at_utc": serialize_snapshot_time(datetime.utcnow()),
        "api_url": api_url,
        "timeout_seconds": timeout_seconds,
        "token_configured": bool(token),
        "token_preview": _mask_secret(token),
        "http_status": None,
        "request_ok": False,
        "cloudflare_success": None,
        "errors": None,
        "payload_summary": None,
        "error": None,
    }

    if not api_url:
        result["error"] = "CLOUDFLARE_RADAR_HTTP_TIMESERIES_URL no configurado"
        return result
    if not token:
        result["error"] = "CF_API_TOKEN no configurado"
        return result

    try:
        response = requests.get(
            api_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout_seconds,
        )
        result["http_status"] = response.status_code
        result["request_ok"] = bool(response.ok)

        payload = None
        try:
            payload = response.json()
        except Exception:
            payload = None

        if isinstance(payload, dict):
            result["cloudflare_success"] = payload.get("success")
            result["errors"] = payload.get("errors")
            result["payload_summary"] = _connectivity_payload_summary(payload)
            if not response.ok and not result["errors"]:
                result["error"] = (response.text or "").strip()[:400]
        else:
            result["error"] = "Respuesta no JSON o invalida"
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _apply_vote(record, value):
    if value == 1:
        record.upvotes = (record.upvotes or 0) + 1
    else:
        record.downvotes = (record.downvotes or 0) + 1


def _remove_vote(record, value):
    if value == 1:
        record.upvotes = max((record.upvotes or 0) - 1, 0)
    else:
        record.downvotes = max((record.downvotes or 0) - 1, 0)


def _get_verified_post_ids(post_ids):
    if not post_ids:
        return set()
    voter_hash = get_voter_hash(current_user, request, current_app.config.get("SECRET_KEY", ""))
    if not voter_hash:
        return set()
    rows = (
        VoteRecord.query.filter_by(target_type="post_verify", voter_hash=voter_hash)
        .filter(VoteRecord.target_id.in_(post_ids))
        .all()
    )
    return {row.target_id for row in rows}


def _average_numeric(values):
    numeric = [to_float(value) for value in (values or [])]
    numeric = [value for value in numeric if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _minimum_numeric(values):
    numeric = [to_float(value) for value in (values or [])]
    numeric = [value for value in numeric if value is not None]
    if not numeric:
        return None
    return min(numeric)


def _parse_connectivity_window_hours():
    raw = (request.args.get("window_hours") or "").strip()
    if not raw:
        return 24
    try:
        value = int(raw)
    except Exception:
        return 24
    if value in (2, 6, 24):
        return value
    return 24


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.route("/connectivity/latest")
@limiter.limit("120/minute")
def connectivity_latest():
    now = datetime.utcnow()
    stale_after_hours = int(current_app.config.get("CONNECTIVITY_STALE_AFTER_HOURS", 8))
    stale_threshold = timedelta(hours=max(stale_after_hours, 1))
    window_hours = _parse_connectivity_window_hours()
    window_start = now - timedelta(hours=window_hours)
    window_aggregation = "worst"

    snapshot = (
        ConnectivitySnapshot.query.options(selectinload(ConnectivitySnapshot.provinces))
        .order_by(ConnectivitySnapshot.observed_at_utc.desc(), ConnectivitySnapshot.id.desc())
        .first()
    )
    window_snapshots = (
        ConnectivitySnapshot.query.options(selectinload(ConnectivitySnapshot.provinces))
        .filter(
            ConnectivitySnapshot.observed_at_utc >= window_start,
            ConnectivitySnapshot.observed_at_utc <= now,
        )
        .order_by(ConnectivitySnapshot.observed_at_utc.asc(), ConnectivitySnapshot.id.asc())
        .all()
    )

    geojson = load_province_geojson()
    try:
        province_names = set(list_provinces() or [])
    except Exception:
        province_names = set(PROVINCES)
    if not province_names:
        province_names = set(PROVINCES)
    province_names.update(province_names_from_geojson(geojson))

    national_score = None
    national_status = STATUS_UNKNOWN
    national_confidence = "unknown"
    stale = True
    partial = True
    snapshot_payload = None
    status_by_province = {}
    window_payload = {
        "hours": window_hours,
        "aggregation": window_aggregation,
        "start_utc": serialize_snapshot_time(window_start),
        "end_utc": serialize_snapshot_time(now),
        "snapshot_count": 0,
        "national_score": None,
        "national_status": STATUS_UNKNOWN,
        "national_status_label": STATUS_LABELS.get(STATUS_UNKNOWN, "Sin datos"),
    }

    if snapshot:
        stale = not snapshot.fetched_at_utc or (now - snapshot.fetched_at_utc) > stale_threshold
        snapshot_payload = {
            "id": snapshot.id,
            "observed_at_utc": serialize_snapshot_time(snapshot.observed_at_utc),
            "fetched_at_utc": serialize_snapshot_time(snapshot.fetched_at_utc),
            "traffic_value": snapshot.traffic_value,
            "baseline_value": snapshot.baseline_value,
            "score": snapshot.score,
            "status": score_to_status(snapshot.score),
            "status_label": STATUS_LABELS.get(
                score_to_status(snapshot.score), STATUS_LABELS[STATUS_UNKNOWN]
            ),
            "is_partial": bool(snapshot.is_partial),
            "stale": stale,
            "confidence": snapshot.confidence or "country_level",
        }

    if window_snapshots:
        national_window_scores = [item.score for item in window_snapshots]
        if window_aggregation == "worst":
            national_score = _minimum_numeric(national_window_scores)
        else:
            national_score = _average_numeric(national_window_scores)

        national_status = score_to_status(national_score)
        national_confidence = "window_worst_country_level"
        partial = bool(any(item.is_partial for item in window_snapshots))

        province_score_map = {}
        for snap in window_snapshots:
            for row in snap.provinces:
                province_score_map.setdefault(row.province, []).append(row.score)
                province_names.add(row.province)

        for province, scores in province_score_map.items():
            if window_aggregation == "worst":
                province_score = _minimum_numeric(scores)
            else:
                province_score = _average_numeric(scores)
            status_key = score_to_status(province_score)
            status_by_province[province] = {
                "province": province,
                "score": province_score,
                "status": status_key,
                "status_label": STATUS_LABELS.get(status_key, STATUS_LABELS[STATUS_UNKNOWN]),
                "status_color": STATUS_COLORS.get(status_key, STATUS_COLORS[STATUS_UNKNOWN]),
                "confidence": "window_worst_estimated_country_level",
                "is_estimated": True,
            }

        window_payload.update(
            {
                "snapshot_count": len(window_snapshots),
                "national_score": national_score,
                "national_status": national_status,
                "national_status_label": STATUS_LABELS.get(
                    national_status, STATUS_LABELS[STATUS_UNKNOWN]
                ),
                "latest_observed_at_utc": serialize_snapshot_time(
                    window_snapshots[-1].observed_at_utc
                ),
            }
        )
    elif snapshot:
        national_score = snapshot.score
        national_status = score_to_status(snapshot.score)
        national_confidence = snapshot.confidence or "country_level"
        partial = bool(snapshot.is_partial)

        for row in snapshot.provinces:
            status_key = score_to_status(row.score)
            status_by_province[row.province] = {
                "province": row.province,
                "score": row.score,
                "status": status_key,
                "status_label": STATUS_LABELS.get(status_key, STATUS_LABELS[STATUS_UNKNOWN]),
                "status_color": STATUS_COLORS.get(status_key, STATUS_COLORS[STATUS_UNKNOWN]),
                "confidence": row.confidence or "estimated_country_level",
                "is_estimated": True,
            }
            province_names.add(row.province)

        window_payload.update(
            {
                "snapshot_count": 1,
                "national_score": national_score,
                "national_status": national_status,
                "national_status_label": STATUS_LABELS.get(
                    national_status, STATUS_LABELS[STATUS_UNKNOWN]
                ),
                "latest_observed_at_utc": serialize_snapshot_time(snapshot.observed_at_utc),
            }
        )

    province_items = []
    for province in sorted(province_names):
        state = status_by_province.get(province)
        if not state:
            status_key = national_status if national_score is not None else STATUS_UNKNOWN
            state = {
                "province": province,
                "score": national_score,
                "status": status_key,
                "status_label": STATUS_LABELS.get(status_key, STATUS_LABELS[STATUS_UNKNOWN]),
                "status_color": STATUS_COLORS.get(status_key, STATUS_COLORS[STATUS_UNKNOWN]),
                "confidence": national_confidence,
                "is_estimated": True,
            }
            status_by_province[province] = state
        province_items.append(state)

    enriched_geojson = enrich_geojson_with_status(geojson, status_by_province)
    http_requests_24h = _build_http_requests_24h_summary()

    return jsonify(
        {
            "snapshot": snapshot_payload,
            "stale": stale,
            "is_partial": partial,
            "has_geojson": bool((enriched_geojson.get("features") or [])),
            "provinces": province_items,
            "geojson": enriched_geojson,
            "window": window_payload,
            "http_requests_24h": http_requests_24h,
            "source": {
                "name": "Cloudflare Radar",
                "url": "https://radar.cloudflare.com/",
                "label": "Hecho con tecnologia de Cloudflare Radar",
            },
            "refresh_seconds": int(current_app.config.get("CONNECTIVITY_FRONTEND_REFRESH_SECONDS", 300)),
        }
    )


@api_bp.route("/connectivity/debug")
@limiter.limit("30/minute")
def connectivity_debug():
    if not _is_admin_user():
        return jsonify({"error": "Acceso denegado"}), 403

    now = datetime.utcnow()
    stale_after_hours = int(current_app.config.get("CONNECTIVITY_STALE_AFTER_HOURS", 8))
    stale_threshold = timedelta(hours=max(stale_after_hours, 1))

    snapshot = (
        ConnectivitySnapshot.query.options(selectinload(ConnectivitySnapshot.provinces))
        .order_by(ConnectivitySnapshot.observed_at_utc.desc(), ConnectivitySnapshot.id.desc())
        .first()
    )
    latest_runs = (
        ConnectivityIngestionRun.query.order_by(
            ConnectivityIngestionRun.started_at_utc.desc(),
            ConnectivityIngestionRun.id.desc(),
        )
        .limit(10)
        .all()
    )

    geojson = load_province_geojson()
    geojson_names = set(province_names_from_geojson(geojson))
    geo_diagnostic = diagnose_province_geojson()

    snapshot_payload = None
    snapshot_stale = True
    province_rows = []
    if snapshot:
        snapshot_stale = not snapshot.fetched_at_utc or (now - snapshot.fetched_at_utc) > stale_threshold
        province_rows = list(snapshot.provinces or [])
        snapshot_payload = {
            "id": snapshot.id,
            "observed_at_utc": serialize_snapshot_time(snapshot.observed_at_utc),
            "fetched_at_utc": serialize_snapshot_time(snapshot.fetched_at_utc),
            "traffic_value": snapshot.traffic_value,
            "baseline_value": snapshot.baseline_value,
            "score": snapshot.score,
            "status": snapshot.status,
            "is_partial": bool(snapshot.is_partial),
            "confidence": snapshot.confidence,
            "method": snapshot.method,
            "stale": snapshot_stale,
            "province_rows_count": len(province_rows),
        }

    province_status_names = {row.province for row in province_rows if row.province}
    missing_geo_for_status = sorted(province_status_names - geojson_names)
    missing_status_for_geo = sorted(geojson_names - province_status_names)

    runs_payload = []
    for run in latest_runs:
        payload_summary = None
        payload_parse_error = None
        if run.payload_json:
            try:
                payload_obj = json.loads(run.payload_json)
                payload_summary = _connectivity_payload_summary(payload_obj)
            except Exception as exc:
                payload_parse_error = str(exc)

        runs_payload.append(
            {
                "id": run.id,
                "status": run.status,
                "attempt_count": run.attempt_count,
                "scheduled_for_utc": serialize_snapshot_time(run.scheduled_for_utc),
                "started_at_utc": serialize_snapshot_time(run.started_at_utc),
                "finished_at_utc": serialize_snapshot_time(run.finished_at_utc),
                "error_message": (run.error_message or "")[:500] or None,
                "payload_parse_error": payload_parse_error,
                "payload_summary": payload_summary,
            }
        )

    diagnostics = {
        "generated_at_utc": serialize_snapshot_time(now),
        "config": {
            "api_url": current_app.config.get("CLOUDFLARE_RADAR_HTTP_TIMESERIES_URL"),
            "cf_api_token_configured": bool(_cf_api_token()),
            "cf_api_token_preview": _mask_secret(_cf_api_token()),
            "connectivity_fetch_delay_seconds": int(current_app.config.get("CONNECTIVITY_FETCH_DELAY_SECONDS", 120)),
            "connectivity_fetch_timeout_seconds": int(current_app.config.get("CONNECTIVITY_FETCH_TIMEOUT_SECONDS", 30)),
            "connectivity_stale_after_hours": stale_after_hours,
            "connectivity_frontend_refresh_seconds": int(
                current_app.config.get("CONNECTIVITY_FRONTEND_REFRESH_SECONDS", 300)
            ),
        },
        "geojson": {
            "has_geojson_features": bool((geojson.get("features") or [])),
            "geojson_feature_count": len(geojson.get("features") or []),
            "geojson_province_name_count": len(geojson_names),
            "diagnostic": geo_diagnostic,
        },
        "snapshot": snapshot_payload,
        "ingestion_runs": runs_payload,
        "consistency": {
            "status_provinces_without_geometry": missing_geo_for_status,
            "geometry_provinces_without_status": missing_status_for_geo,
            "status_geometry_overlap_count": len(province_status_names & geojson_names),
            "likely_reasons_if_not_drawn": [
                "No existe snapshot en BD" if not snapshot else None,
                "Snapshot existe pero esta stale (sin datos recientes)" if snapshot_stale else None,
                "GeoJSON provincial vacio o ruta incorrecta"
                if not (geojson.get("features") or [])
                else None,
                "Nombres de provincias no coinciden entre BD y GeoJSON"
                if province_rows and not (province_status_names & geojson_names)
                else None,
            ],
        },
    }
    diagnostics["consistency"]["likely_reasons_if_not_drawn"] = [
        item for item in diagnostics["consistency"]["likely_reasons_if_not_drawn"] if item
    ]

    if _truthy_param(request.args.get("probe")):
        diagnostics["cloudflare_probe"] = _cloudflare_probe()

    return jsonify(diagnostics)


@api_bp.route("/push/subscribe", methods=["POST"])
@limiter.limit("5/minute; 60/day")
def push_subscribe():
    if not _push_enabled():
        return jsonify({"error": "Push deshabilitado"}), 503

    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()

    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Suscripción inválida"}), 400
    if len(endpoint) > 2000 or len(p256dh) > 255 or len(auth) > 255:
        return jsonify({"error": "Suscripción inválida"}), 400

    user_agent = (request.headers.get("User-Agent") or "")[:255]
    subscription = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if subscription:
        subscription.p256dh = p256dh
        subscription.auth = auth
        subscription.active = True
        subscription.user_agent = user_agent
    else:
        subscription = PushSubscription(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent,
            active=True,
        )
        db.session.add(subscription)

    db.session.commit()
    return jsonify({"status": "ok"})


@api_bp.route("/push/unsubscribe", methods=["POST"])
@limiter.limit("10/minute; 120/day")
def push_unsubscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get("endpoint") or "").strip()
    if not endpoint:
        return jsonify({"error": "Suscripción inválida"}), 400

    subscription = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if subscription:
        subscription.active = False
        subscription.updated_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"status": "ok"})


@api_bp.route("/categories")
def categories():
    items = Category.query.order_by(Category.id.asc()).all()
    return jsonify(
        [
            {"id": c.id, "name": c.name, "slug": c.slug, "description": c.description}
            for c in items
        ]
    )


@api_bp.route("/posts")
def posts():
    category_id = request.args.get("category_id")
    limit = request.args.get("limit")
    query = Post.query.options(selectinload(Post.media)).filter_by(status="approved")
    if category_id:
        query = query.filter_by(category_id=int(category_id))

    query = query.order_by(Post.created_at.desc())
    if limit:
        try:
            query = query.limit(int(limit))
        except ValueError:
            pass

    items = query.all()
    verified_ids = _get_verified_post_ids([p.id for p in items])
    return jsonify(
        [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "latitude": float(p.latitude),
                "longitude": float(p.longitude),
                "address": p.address,
                "province": p.province,
                "municipality": p.municipality,
                "movement_at": p.movement_at.isoformat() if p.movement_at else None,
                "repressor_name": p.repressor_name,
                "other_type": p.other_type,
                "created_at": p.created_at.isoformat(),
                "anon": f"Anon-{p.author.anon_code}" if p.author and p.author.anon_code else "Anon",
                "polygon_geojson": p.polygon_geojson,
                "links": json.loads(p.links_json) if p.links_json else [],
                "media": get_media_payload(p)[:4],
                "verify_count": p.verify_count or 0,
                "verified_by_me": p.id in verified_ids,
                "category": {
                    "id": p.category.id,
                    "name": p.category.name,
                    "slug": p.category.slug,
                },
            }
            for p in items
        ]
    )


def _serialize_post(post: Post):
    return {
        "id": post.id,
        "title": post.title,
        "description": post.description,
        "latitude": float(post.latitude),
        "longitude": float(post.longitude),
        "address": post.address,
        "province": post.province,
        "municipality": post.municipality,
        "movement_at": post.movement_at.isoformat() if post.movement_at else None,
        "repressor_name": post.repressor_name,
        "other_type": post.other_type,
        "status": post.status,
        "polygon_geojson": post.polygon_geojson,
        "links": json.loads(post.links_json) if post.links_json else [],
        "media": get_media_payload(post),
        "verify_count": post.verify_count or 0,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "anon": f"Anon-{post.author.anon_code}" if post.author and post.author.anon_code else "Anon",
        "category": {
            "id": post.category.id,
            "name": post.category.name,
            "slug": post.category.slug,
        }
        if post.category
        else None,
    }


@api_bp.route("/v1/reports")
@limiter.limit("120/minute")
def reports_v1():
    category_id = request.args.get("category_id")
    province = (request.args.get("province") or "").strip()
    municipality = (request.args.get("municipality") or "").strip()
    status = (request.args.get("status") or "approved").strip().lower()

    allowed_statuses = {"pending", "approved", "rejected", "hidden", "deleted"}
    if status not in allowed_statuses:
        status = "approved"

    if status != "approved" and not _is_admin_user():
        status = "approved"

    query = Post.query.options(
        selectinload(Post.media),
        selectinload(Post.category),
        selectinload(Post.author),
    )
    query = query.filter(Post.status == status)

    if category_id:
        try:
            query = query.filter(Post.category_id == int(category_id))
        except ValueError:
            pass

    if province:
        query = query.filter(Post.province.ilike(province))
    if municipality:
        query = query.filter(Post.municipality.ilike(municipality))

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    try:
        per_page = max(int(request.args.get("per_page", 50)), 1)
    except ValueError:
        per_page = 50
    per_page = min(per_page, 100)

    total = query.count()
    pages = max(math.ceil(total / per_page), 1) if per_page else 1
    items = (
        query.order_by(Post.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify(
        {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
            "items": [_serialize_post(p) for p in items],
        }
    )


@api_bp.route("/v1/reports/<int:post_id>")
@limiter.limit("120/minute")
def report_detail_v1(post_id):
    query = Post.query.options(
        selectinload(Post.media),
        selectinload(Post.category),
        selectinload(Post.author),
    )
    post = query.get_or_404(post_id)
    if post.status != "approved" and not _is_admin_user():
        return jsonify({"error": "No autorizado."}), 403
    return jsonify(_serialize_post(post))


@api_bp.route("/v1/categories")
def categories_v1():
    return categories()


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


def _build_connectivity_outage_events(start_dt, end_dt, province=""):
    selected_province = (province or "").strip() or None

    if selected_province:
        base_query = db.session.query(
            ConnectivitySnapshot.id.label("snapshot_id"),
            ConnectivitySnapshot.observed_at_utc.label("observed_at_utc"),
            ConnectivityProvinceStatus.status.label("status"),
            ConnectivityProvinceStatus.score.label("score"),
            ConnectivityProvinceStatus.province.label("province"),
        ).join(
            ConnectivityProvinceStatus,
            ConnectivityProvinceStatus.snapshot_id == ConnectivitySnapshot.id,
        ).filter(
            ConnectivityProvinceStatus.province == selected_province,
        )
    else:
        base_query = db.session.query(
            ConnectivitySnapshot.id.label("snapshot_id"),
            ConnectivitySnapshot.observed_at_utc.label("observed_at_utc"),
            ConnectivitySnapshot.status.label("status"),
            ConnectivitySnapshot.score.label("score"),
        )

    previous_point = (
        base_query.filter(ConnectivitySnapshot.observed_at_utc < start_dt)
        .order_by(ConnectivitySnapshot.observed_at_utc.desc(), ConnectivitySnapshot.id.desc())
        .first()
    )
    points_in_range = (
        base_query.filter(
            ConnectivitySnapshot.observed_at_utc >= start_dt,
            ConnectivitySnapshot.observed_at_utc <= end_dt,
        )
        .order_by(ConnectivitySnapshot.observed_at_utc.asc(), ConnectivitySnapshot.id.asc())
        .all()
    )

    points = []
    if previous_point:
        points.append(previous_point)
    points.extend(points_in_range)

    if not points:
        return {"events": [], "total": 0, "ongoing": 0}

    def _is_critical(item):
        return (getattr(item, "status", "") or "").strip().lower() == STATUS_CRITICAL

    def _build_event_start(item):
        start_raw = getattr(item, "observed_at_utc", None)
        event = {
            "started_at_utc": serialize_snapshot_time(start_raw),
            "ended_at_utc": None,
            "duration_minutes": None,
            "ongoing": True,
            "score_at_start": getattr(item, "score", None),
            "score_at_end": None,
            "start_snapshot_id": getattr(item, "snapshot_id", None),
            "end_snapshot_id": None,
            "province": getattr(item, "province", None) or selected_province,
            "_start_dt": start_raw,
        }
        return event

    events = []
    open_event = None
    prev = None
    for point in points:
        current_critical = _is_critical(point)
        previous_critical = _is_critical(prev) if prev is not None else False

        if current_critical and not previous_critical:
            open_event = _build_event_start(point)
        elif (not current_critical) and previous_critical and open_event is not None:
            start_raw = open_event.get("_start_dt")
            end_raw = getattr(point, "observed_at_utc", None)
            duration_minutes = None
            if start_raw and end_raw:
                duration_minutes = max(int((end_raw - start_raw).total_seconds() // 60), 0)

            open_event.update(
                {
                    "ended_at_utc": serialize_snapshot_time(end_raw),
                    "duration_minutes": duration_minutes,
                    "ongoing": False,
                    "score_at_end": getattr(point, "score", None),
                    "end_snapshot_id": getattr(point, "snapshot_id", None),
                }
            )
            open_event.pop("_start_dt", None)
            events.append(open_event)
            open_event = None

        prev = point

    if open_event is not None:
        open_event.pop("_start_dt", None)
        events.append(open_event)

    events = [event for event in events if event.get("started_at_utc")]
    events.sort(key=lambda event: event.get("started_at_utc") or "", reverse=True)
    return {
        "events": events[:120],
        "total": len(events),
        "ongoing": len([event for event in events if event.get("ongoing")]),
    }


@api_bp.route("/v1/analytics")
@limiter.limit("60/minute")
def analytics_v1():
    start_raw = (request.args.get("start") or "").strip()
    end_raw = (request.args.get("end") or "").strip()
    category_id = request.args.get("category_id")
    province = (request.args.get("province") or "").strip()

    end_dt = _parse_date(end_raw) or datetime.utcnow()
    start_dt = _parse_date(start_raw) or (end_dt - timedelta(days=90))
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)

    active_statuses = ["approved", "pending", "rejected", "hidden"]

    base_query = Post.query.filter(
        Post.created_at >= start_dt,
        Post.created_at <= end_dt,
        Post.status.in_(active_statuses),
    )
    if category_id:
        try:
            base_query = base_query.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        base_query = base_query.filter(Post.province == province)

    day_expr = func.date(Post.created_at).label("day")
    reports_over_time = (
        db.session.query(
            day_expr,
            func.count(Post.id),
        )
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
        )
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if category_id:
        try:
            reports_over_time = reports_over_time.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        reports_over_time = reports_over_time.filter(Post.province == province)

    reports_series = [
        {"date": row[0].isoformat(), "count": row[1]}
        for row in reports_over_time.all()
    ]

    category_distribution = (
        db.session.query(Category.id, Category.name, func.count(Post.id))
        .join(Post, Post.category_id == Category.id)
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
        )
        .group_by(Category.id, Category.name)
        .order_by(func.count(Post.id).desc())
    )
    if category_id:
        try:
            category_distribution = category_distribution.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        category_distribution = category_distribution.filter(Post.province == province)

    category_items = [
        {"id": row[0], "name": row[1], "count": row[2]}
        for row in category_distribution.all()
    ]

    province_distribution = (
        db.session.query(Post.province, func.count(Post.id))
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
            Post.province.isnot(None),
            Post.province != "",
        )
        .group_by(Post.province)
        .order_by(func.count(Post.id).desc())
    )
    if category_id:
        try:
            province_distribution = province_distribution.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        province_distribution = province_distribution.filter(Post.province == province)

    province_items = [
        {"name": row[0], "count": row[1]} for row in province_distribution.limit(10).all()
    ]

    municipality_distribution = (
        db.session.query(Post.municipality, func.count(Post.id))
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
            Post.municipality.isnot(None),
            Post.municipality != "",
        )
        .group_by(Post.municipality)
        .order_by(func.count(Post.id).desc())
    )
    if category_id:
        try:
            municipality_distribution = municipality_distribution.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        municipality_distribution = municipality_distribution.filter(Post.province == province)

    municipality_items = [
        {"name": row[0], "count": row[1]} for row in municipality_distribution.limit(10).all()
    ]

    moderation_status = (
        db.session.query(Post.status, func.count(Post.id))
        .filter(Post.created_at >= start_dt, Post.created_at <= end_dt)
        .group_by(Post.status)
        .all()
    )
    moderation_map = {status: count for status, count in moderation_status}

    top_verified = (
        Post.query.options(selectinload(Post.category))
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status == "approved",
        )
        .order_by(Post.verify_count.desc().nullslast(), Post.created_at.desc())
    )
    if category_id:
        try:
            top_verified = top_verified.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        top_verified = top_verified.filter(Post.province == province)

    top_verified_items = [
        {"id": p.id, "title": p.title, "verify_count": p.verify_count or 0}
        for p in top_verified.limit(10).all()
    ]

    comment_day = func.date(Comment.created_at).label("day")
    comment_query = (
        db.session.query(
            comment_day,
            func.count(Comment.id),
        )
        .filter(Comment.created_at >= start_dt, Comment.created_at <= end_dt)
        .group_by(comment_day)
        .order_by(comment_day)
    )
    discussion_day = func.date(DiscussionComment.created_at).label("day")
    discussion_comment_query = (
        db.session.query(
            discussion_day,
            func.count(DiscussionComment.id),
        )
        .filter(
            DiscussionComment.created_at >= start_dt,
            DiscussionComment.created_at <= end_dt,
        )
        .group_by(discussion_day)
        .order_by(discussion_day)
    )

    report_comments = {row[0].isoformat(): row[1] for row in comment_query.all()}
    discussion_comments = {
        row[0].isoformat(): row[1] for row in discussion_comment_query.all()
    }
    labels = sorted(set(report_comments.keys()) | set(discussion_comments.keys()))
    report_counts = [report_comments.get(label, 0) for label in labels]
    discussion_counts = [discussion_comments.get(label, 0) for label in labels]

    edit_status_query = (
        db.session.query(PostEditRequest.status, func.count(PostEditRequest.id))
        .filter(PostEditRequest.created_at >= start_dt, PostEditRequest.created_at <= end_dt)
        .group_by(PostEditRequest.status)
        .all()
    )
    edit_status_map = {status: count for status, count in edit_status_query}
    connectivity_outages = _build_connectivity_outage_events(start_dt, end_dt, province=province)
    connectivity_24h = _build_http_requests_24h_summary()

    return jsonify(
        {
            "range": {
                "start": start_dt.date().isoformat(),
                "end": end_dt.date().isoformat(),
            },
            "reports_over_time": reports_series,
            "category_distribution": category_items,
            "province_distribution": province_items,
            "municipality_distribution": municipality_items,
            "moderation_status": {
                "approved": moderation_map.get("approved", 0),
                "pending": moderation_map.get("pending", 0),
                "rejected": moderation_map.get("rejected", 0),
                "hidden": moderation_map.get("hidden", 0),
            },
            "top_verified": top_verified_items,
            "comments_over_time": {
                "labels": labels,
                "report_counts": report_counts,
                "discussion_counts": discussion_counts,
            },
            "edit_status": {
                "pending": edit_status_map.get("pending", 0),
                "approved": edit_status_map.get("approved", 0),
                "rejected": edit_status_map.get("rejected", 0),
            },
            "connectivity_outages": connectivity_outages,
            "connectivity_24h": connectivity_24h,
        }
    )


def _get_or_create_anon_user():
    if current_user.is_authenticated:
        return current_user
    anon_user = User(email=f"anon+{secrets.token_hex(6)}@local")
    anon_user.set_password(secrets.token_urlsafe(16))
    anon_user.ensure_anon_code()
    default_role = Role.query.filter_by(name="colaborador").first()
    if default_role:
        anon_user.roles.append(default_role)
    db.session.add(anon_user)
    db.session.flush()
    return anon_user


@api_bp.route("/posts/<int:post_id>/verify", methods=["POST"])
@limiter.limit("10/minute; 200/day")
def verify_post(post_id):
    post = Post.query.get_or_404(post_id)
    cookie_key = f"verified_{post_id}"
    voter_hash = get_voter_hash(current_user, request, current_app.config.get("SECRET_KEY", ""))

    existing = VoteRecord.query.filter_by(
        target_type="post_verify",
        target_id=post.id,
        voter_hash=voter_hash,
    ).first()
    if existing or request.cookies.get(cookie_key):
        return jsonify({"ok": False, "verify_count": post.verify_count or 0})

    record = VoteRecord(
        target_type="post_verify",
        target_id=post.id,
        voter_hash=voter_hash,
        value=1,
    )
    db.session.add(record)
    post.verify_count = (post.verify_count or 0) + 1
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"ok": False, "verify_count": post.verify_count or 0})

    resp = make_response(jsonify({"ok": True, "verify_count": post.verify_count}))
    resp.set_cookie(cookie_key, "1")
    return resp


@api_bp.route("/posts/<int:post_id>/comments", methods=["GET", "POST"])
@limiter.limit("10/minute; 200/day", methods=["POST"])
def comments(post_id):
    post = Post.query.get_or_404(post_id)
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        body = sanitize_text(data.get("body") or "", max_len=4000)
        if recaptcha_enabled():
            token = (data.get("recaptcha") or "").strip()
            if not verify_recaptcha(token, request.remote_addr):
                return jsonify({"ok": False, "error": "Verificación reCAPTCHA falló."}), 400
        if has_malicious_input([body]):
            return jsonify({"ok": False, "error": "Contenido sospechoso."}), 400
        if not body:
            return jsonify({"ok": False, "error": "Comentario vacío."}), 400

        user = _get_or_create_anon_user()
        label = f"Anon-{user.anon_code}" if user and user.anon_code else "Anon"
        comment = Comment(post_id=post.id, author_id=user.id, author_label=label, body=body)
        db.session.add(comment)
        db.session.commit()

    items = (
        Comment.query.filter_by(post_id=post.id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": c.id,
                "author": c.author_label or "Anon",
                "body": c.body,
                "created_at": c.created_at.isoformat(),
                "upvotes": c.upvotes or 0,
                "downvotes": c.downvotes or 0,
                "score": (c.upvotes or 0) - (c.downvotes or 0),
            }
            for c in items
        ]
    )


@api_bp.route("/comments/<int:comment_id>/vote", methods=["POST"])
@limiter.limit("10/minute; 200/day")
def vote_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        return jsonify({"ok": False, "error": "Voto inválido."}), 400

    voter_hash = get_voter_hash(current_user, request, current_app.config.get("SECRET_KEY", ""))
    existing = VoteRecord.query.filter_by(
        target_type="comment",
        target_id=comment.id,
        voter_hash=voter_hash,
    ).first()

    if existing and existing.value == value:
        return jsonify(
            {
                "ok": True,
                "upvotes": comment.upvotes or 0,
                "downvotes": comment.downvotes or 0,
                "score": (comment.upvotes or 0) - (comment.downvotes or 0),
            }
        )

    if existing:
        _remove_vote(comment, existing.value)
        existing.value = value
    else:
        existing = VoteRecord(
            target_type="comment",
            target_id=comment.id,
            voter_hash=voter_hash,
            value=value,
        )
        db.session.add(existing)

    _apply_vote(comment, value)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "upvotes": comment.upvotes or 0,
            "downvotes": comment.downvotes or 0,
            "score": (comment.upvotes or 0) - (comment.downvotes or 0),
        }
    )


@api_bp.route("/comments/<int:comment_id>", methods=["DELETE"])
@limiter.limit("10/minute; 100/day")
def delete_comment(comment_id):
    if not (current_user.is_authenticated and current_user.has_role("administrador")):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/posts/<int:post_id>/status", methods=["POST"])
def update_post_status(post_id):
    if not (current_user.is_authenticated and current_user.has_role("administrador")):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"approved", "hidden", "deleted", "rejected", "pending"}:
        return jsonify({"ok": False, "error": "Estado inválido."}), 400
    post = Post.query.get_or_404(post_id)
    post.status = status
    db.session.commit()
    return jsonify({"ok": True, "status": post.status})


@api_bp.route("/discusiones/<int:post_id>/vote", methods=["POST"])
@limiter.limit("12/minute; 240/day")
def vote_discussion_post(post_id):
    post = DiscussionPost.query.get_or_404(post_id)
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        return jsonify({"ok": False, "error": "Voto inválido."}), 400

    voter_hash = get_voter_hash(current_user, request, current_app.config.get("SECRET_KEY", ""))
    existing = VoteRecord.query.filter_by(
        target_type="discussion_post",
        target_id=post.id,
        voter_hash=voter_hash,
    ).first()

    if existing and existing.value == value:
        return jsonify(
            {
                "ok": True,
                "upvotes": post.upvotes or 0,
                "downvotes": post.downvotes or 0,
                "score": (post.upvotes or 0) - (post.downvotes or 0),
            }
        )

    if existing:
        _remove_vote(post, existing.value)
        existing.value = value
    else:
        existing = VoteRecord(
            target_type="discussion_post",
            target_id=post.id,
            voter_hash=voter_hash,
            value=value,
        )
        db.session.add(existing)

    _apply_vote(post, value)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "upvotes": post.upvotes or 0,
            "downvotes": post.downvotes or 0,
            "score": (post.upvotes or 0) - (post.downvotes or 0),
        }
    )


@api_bp.route("/discusiones/comentarios/<int:comment_id>/vote", methods=["POST"])
@limiter.limit("10/minute; 200/day")
def vote_discussion_comment(comment_id):
    comment = DiscussionComment.query.get_or_404(comment_id)
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        return jsonify({"ok": False, "error": "Voto inválido."}), 400

    voter_hash = get_voter_hash(current_user, request, current_app.config.get("SECRET_KEY", ""))
    existing = VoteRecord.query.filter_by(
        target_type="discussion_comment",
        target_id=comment.id,
        voter_hash=voter_hash,
    ).first()

    if existing and existing.value == value:
        return jsonify(
            {
                "ok": True,
                "upvotes": comment.upvotes or 0,
                "downvotes": comment.downvotes or 0,
                "score": (comment.upvotes or 0) - (comment.downvotes or 0),
            }
        )

    if existing:
        _remove_vote(comment, existing.value)
        existing.value = value
    else:
        existing = VoteRecord(
            target_type="discussion_comment",
            target_id=comment.id,
            voter_hash=voter_hash,
            value=value,
        )
        db.session.add(existing)

    _apply_vote(comment, value)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "upvotes": comment.upvotes or 0,
            "downvotes": comment.downvotes or 0,
            "score": (comment.upvotes or 0) - (comment.downvotes or 0),
        }
    )


@api_bp.route("/posts/<int:post_id>/media", methods=["POST"])
@limiter.limit("6/hour; 30/day")
def upload_post_media(post_id):
    post = Post.query.get_or_404(post_id)
    files = [
        file
        for file in request.files.getlist("images")
        if file and (file.filename or "").strip()
    ]
    captions_raw = request.form.getlist("image_captions[]")
    if has_malicious_input(captions_raw):
        return jsonify({"ok": False, "error": "Contenido sospechoso."}), 400
    ok, error = validate_files(files)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400

    moderation_setting = SiteSetting.query.filter_by(key="moderation_enabled").first()
    moderation_enabled = True
    if moderation_setting:
        moderation_enabled = moderation_setting.value == "true"

    urls = upload_files(files)
    if not urls:
        return jsonify({"ok": False, "error": "No se pudo subir la imagen."}), 400

    if moderation_enabled:
        captions = []
        for idx in range(len(urls)):
            value = ""
            if idx < len(captions_raw):
                value = (captions_raw[idx] or "").strip()
            captions.append(value[:255] if value else "")
        new_items = [
            {"url": url, "caption": (captions[idx] if idx < len(captions) else "")}
            for idx, url in enumerate(urls)
        ]
        combined = get_media_payload(post) + new_items
        edit = PostEditRequest(
            post_id=post.id,
            editor_id=current_user.id if current_user.is_authenticated else None,
            editor_label=f"Anon-{current_user.anon_code}" if current_user.is_authenticated and current_user.anon_code else "Anon",
            reason="Imagen añadida",
            title=post.title,
            description=post.description,
            latitude=post.latitude,
            longitude=post.longitude,
            address=post.address,
            province=post.province,
            municipality=post.municipality,
            repressor_name=post.repressor_name,
            other_type=post.other_type,
            category_id=post.category_id,
            polygon_geojson=post.polygon_geojson,
            links_json=post.links_json,
            media_json=json.dumps(combined),
        )
        db.session.add(edit)
        db.session.commit()
        return jsonify({"ok": True, "status": "pending"})

    revision = PostRevision(
        post_id=post.id,
        editor_id=current_user.id if current_user.is_authenticated else None,
        editor_label=f"Anon-{current_user.anon_code}" if current_user.is_authenticated and current_user.anon_code else "Anon",
        reason="Imagen añadida",
        title=post.title,
        description=post.description,
        latitude=post.latitude,
        longitude=post.longitude,
        address=post.address,
        province=post.province,
        municipality=post.municipality,
        repressor_name=post.repressor_name,
        other_type=post.other_type,
        category_id=post.category_id,
        polygon_geojson=post.polygon_geojson,
        links_json=post.links_json,
        media_json=media_json_from_post(post),
    )
    db.session.add(revision)

    captions = []
    for idx in range(len(urls)):
        value = ""
        if idx < len(captions_raw):
            value = (captions_raw[idx] or "").strip()
        captions.append(value[:255] if value else "")

    for idx, url in enumerate(urls):
        caption = captions[idx] if idx < len(captions) else ""
        db.session.add(Media(post_id=post.id, file_url=url, caption=caption or None))
    db.session.commit()

    return jsonify({"ok": True, "status": "approved", "media": get_media_payload(post)})


@api_bp.route("/chat", methods=["GET", "POST"])
@limiter.limit("60/minute", methods=["GET"])
@limiter.limit("6/minute; 120/day", methods=["POST"])
def chat_messages():
    if current_app.config.get("CHAT_DISABLED", True):
        return jsonify({"ok": False, "error": "Chat deshabilitado."}), 403
    now = datetime.utcnow()
    cutoff_keep = now - timedelta(hours=48)
    cutoff_visible = now - timedelta(hours=24)
    cutoff_online = now - timedelta(minutes=10)

    ChatMessage.query.filter(ChatMessage.created_at < cutoff_keep).delete()
    ChatPresence.query.filter(ChatPresence.last_seen < cutoff_online).delete()
    db.session.commit()

    session_id = session.get("chat_sid")
    if not session_id:
        session_id = secrets.token_hex(16)
        session["chat_sid"] = session_id

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        body = sanitize_text(data.get("body") or "", max_len=1000)
        nickname = sanitize_text(data.get("nickname") or "", max_len=80)

        if has_malicious_input([body, nickname]):
            return jsonify({"ok": False, "error": "Contenido sospechoso."}), 400

        if not body:
            return jsonify({"ok": False, "error": "Mensaje vacío."}), 400

        nickname = _sanitize_nick(nickname, _get_chat_nick())
        session["chat_nick"] = nickname

        presence = ChatPresence.query.filter_by(session_id=session_id).first()
        if not presence:
            presence = ChatPresence(session_id=session_id, nickname=nickname, last_seen=now)
            db.session.add(presence)
        else:
            presence.nickname = nickname
            presence.last_seen = now

        author_id = current_user.id if current_user.is_authenticated else None
        msg = ChatMessage(author_id=author_id, author_label=nickname, body=body)
        db.session.add(msg)
        db.session.commit()
    else:
        nickname = _get_chat_nick()
        presence = ChatPresence.query.filter_by(session_id=session_id).first()
        if not presence:
            presence = ChatPresence(session_id=session_id, nickname=nickname, last_seen=now)
            db.session.add(presence)
        else:
            presence.last_seen = now
        db.session.commit()

    items = (
        ChatMessage.query.filter(ChatMessage.created_at >= cutoff_visible)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    online_count = ChatPresence.query.count()
    return jsonify(
        {
            "items": [
                {
                    "id": m.id,
                    "author": m.author_label,
                    "body": m.body,
                    "created_at": m.created_at.isoformat(),
                }
                for m in items
            ],
            "online_count": online_count,
        }
    )
