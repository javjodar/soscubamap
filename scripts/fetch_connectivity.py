import argparse
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from app import create_app
from app.extensions import db
from app.models.connectivity_ingestion_run import ConnectivityIngestionRun
from app.models.connectivity_province_status import ConnectivityProvinceStatus
from app.models.connectivity_snapshot import ConnectivitySnapshot
from app.services.connectivity import (
    compute_connectivity_score,
    extract_series_points,
    get_latest_common_point,
    get_latest_hourly_point,
    median_baseline,
    score_to_status,
    serialize_snapshot_time,
    to_float,
)
from app.services.cuba_locations import PROVINCES, PROVINCE_RADAR_GEOIDS
from app.services.geo_lookup import list_provinces


def parse_args():
    parser = argparse.ArgumentParser(description="Ingesta de conectividad desde Cloudflare Radar")
    parser.add_argument(
        "--single-call",
        action="store_true",
        help="Realiza una sola llamada a Radar (sin segunda consulta con delay)",
    )
    parser.add_argument(
        "--scheduled-for",
        default="",
        help="Timestamp UTC programado para trazabilidad (ISO8601)",
    )
    return parser.parse_args()


def _parse_scheduled_for(raw):
    text = (raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _normalize_name(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def _province_geoids():
    env_raw = (os.getenv("CF_RADAR_PROVINCE_GEOIDS_JSON") or "").strip()
    base = dict(PROVINCE_RADAR_GEOIDS)
    if not env_raw:
        return base

    try:
        payload = json.loads(env_raw)
    except Exception:
        return base
    if not isinstance(payload, dict):
        return base

    normalized = {_normalize_name(name): name for name in PROVINCES}
    merged = dict(base)
    for raw_name, raw_id in payload.items():
        name = normalized.get(_normalize_name(raw_name), str(raw_name or "").strip())
        try:
            geo_id = int(str(raw_id).strip())
        except Exception:
            continue
        if name:
            merged[name] = geo_id
    return merged


def _url_with_geoid(base_url, geo_id):
    text = (base_url or "").strip()
    if not text:
        return text
    parsed = urlparse(text)
    query_pairs = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "geoId"]
    query_pairs.append(("geoId", str(geo_id)))
    query_pairs.append(("geoId", str(geo_id)))
    new_query = urlencode(query_pairs, doseq=True)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def _fetch_once(url, token, timeout_seconds):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    started = datetime.utcnow()
    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
        text = response.text or ""
        payload = None
        try:
            payload = response.json()
        except Exception:
            payload = None

        success_flag = True
        errors = None
        if isinstance(payload, dict) and "success" in payload:
            success_flag = bool(payload.get("success"))
            errors = payload.get("errors")

        ok = response.ok and success_flag and isinstance(payload, dict)
        error_message = None
        if not ok:
            if errors:
                error_message = str(errors)
            elif text:
                error_message = text[:400]
            else:
                error_message = f"HTTP {response.status_code}"

        return {
            "ok": ok,
            "status_code": response.status_code,
            "payload": payload,
            "error": error_message,
            "started_at": started,
            "finished_at": datetime.utcnow(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "payload": None,
            "error": str(exc),
            "started_at": started,
            "finished_at": datetime.utcnow(),
        }


def _pick_best_attempt(attempts):
    best = None
    for attempt in attempts:
        if not attempt.get("ok"):
            continue
        payload = attempt.get("payload")
        latest = get_latest_hourly_point(payload, "main")
        if not latest:
            continue
        candidate = {
            "attempt": attempt,
            "latest": latest,
        }
        if best is None or latest["timestamp"] > best["latest"]["timestamp"]:
            best = candidate
    return best


def _historical_baseline():
    rows = (
        ConnectivitySnapshot.query.order_by(ConnectivitySnapshot.observed_at_utc.desc())
        .limit(12)
        .all()
    )
    return median_baseline([row.traffic_value for row in rows])


def _compute_payload_snapshot(payload):
    main_points = extract_series_points(payload, "main")
    previous_points = extract_series_points(payload, "previous")
    if not main_points:
        return None

    latest_main = main_points[-1]
    latest_pair = get_latest_common_point(main_points, previous_points)

    observed_at = latest_main["timestamp"]
    traffic_value = to_float(latest_main["value"])
    baseline_value = None
    partial = False

    if latest_pair:
        observed_at = latest_pair["timestamp"]
        traffic_value = to_float(latest_pair["main_value"])
        baseline_value = to_float(latest_pair["previous_value"])
    else:
        partial = True
        if previous_points:
            baseline_value = to_float(previous_points[-1]["value"])

    if baseline_value is None or baseline_value <= 0:
        fallback_baseline = _historical_baseline()
        if fallback_baseline is not None and fallback_baseline > 0:
            baseline_value = fallback_baseline
        else:
            baseline_value = traffic_value

    score, status = compute_connectivity_score(traffic_value, baseline_value)
    if score is None:
        return None

    return {
        "observed_at_utc": observed_at,
        "traffic_value": traffic_value,
        "baseline_value": baseline_value,
        "score": score,
        "status": status,
        "is_partial": partial,
    }


def _upsert_snapshot(run, best_payloads_by_province):
    try:
        provinces = list_provinces() or list(PROVINCES)
    except Exception:
        provinces = list(PROVINCES)
    if not provinces:
        provinces = list(PROVINCES)

    province_rows = {}
    for province in provinces:
        payload = (best_payloads_by_province.get(province) or {}).get("payload")
        row = _compute_payload_snapshot(payload) if payload else None
        if row:
            province_rows[province] = row

    if not province_rows:
        return None, "No se encontraron datapoints en ninguna provincia"

    scores = [row["score"] for row in province_rows.values() if row.get("score") is not None]
    traffic_values = [
        row["traffic_value"] for row in province_rows.values() if row.get("traffic_value") is not None
    ]
    baseline_values = [
        row["baseline_value"] for row in province_rows.values() if row.get("baseline_value") is not None
    ]
    observed_candidates = [
        row["observed_at_utc"] for row in province_rows.values() if row.get("observed_at_utc") is not None
    ]

    if not scores or not observed_candidates:
        return None, "No fue posible calcular el score de conectividad"

    score = sum(scores) / len(scores)
    status = score_to_status(score)
    traffic_value = sum(traffic_values) / len(traffic_values) if traffic_values else 0.0
    baseline_value = sum(baseline_values) / len(baseline_values) if baseline_values else traffic_value
    observed_at = max(observed_candidates)
    partial = bool(len(province_rows) < len(provinces)) or any(
        bool(row.get("is_partial")) for row in province_rows.values()
    )

    previous_snapshot = (
        ConnectivitySnapshot.query.order_by(ConnectivitySnapshot.observed_at_utc.desc()).first()
    )
    if previous_snapshot:
        previous_score = to_float(previous_snapshot.score)
        if previous_score is not None and abs(score - previous_score) < 3:
            score = previous_score
            status = score_to_status(score)

    snapshot = ConnectivitySnapshot(
        ingestion_run_id=run.id,
        observed_at_utc=observed_at,
        fetched_at_utc=datetime.utcnow(),
        traffic_value=traffic_value,
        baseline_value=baseline_value,
        score=score,
        status=status,
        is_partial=partial,
        confidence="country_level",
        method="province_geoid_aggregate_v1",
    )
    db.session.add(snapshot)
    db.session.flush()

    for province in provinces:
        row = province_rows.get(province)
        province_score = row["score"] if row else score
        province_status = row["status"] if row else status
        db.session.add(
            ConnectivityProvinceStatus(
                snapshot_id=snapshot.id,
                province=province,
                score=province_score,
                status=province_status,
                confidence=(
                    "province_level_radar_estimated"
                    if row
                    else "country_level_fallback"
                ),
                method="province_geoid_v1" if row else "country_fallback_v1",
            )
        )

    return snapshot, None


def run_ingestion(single_call=False, scheduled_for=None):
    app = create_app()
    with app.app_context():
        token = (os.getenv("CF_API_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("CF_API_TOKEN no configurado")

        api_url = app.config.get("CLOUDFLARE_RADAR_HTTP_TIMESERIES_URL")
        timeout_seconds = int(app.config.get("CONNECTIVITY_FETCH_TIMEOUT_SECONDS", 30))
        delay_seconds = int(app.config.get("CONNECTIVITY_FETCH_DELAY_SECONDS", 120))
        province_geoids = _province_geoids()
        if not province_geoids:
            raise RuntimeError("No hay geoIds provinciales configurados para Radar")

        run = ConnectivityIngestionRun(
            scheduled_for_utc=scheduled_for,
            started_at_utc=datetime.utcnow(),
            status="running",
            attempt_count=0,
            api_url=api_url,
        )
        db.session.add(run)
        db.session.commit()

        attempt_rounds = []
        total_attempts = 0
        max_rounds = 1 if single_call else 2

        for round_index in range(max_rounds):
            round_attempts = {}
            for province, geo_id in province_geoids.items():
                province_url = _url_with_geoid(api_url, geo_id)
                attempt = _fetch_once(province_url, token, timeout_seconds)
                attempt["geo_id"] = geo_id
                attempt["url"] = province_url
                round_attempts[province] = attempt
                total_attempts += 1
            attempt_rounds.append(round_attempts)
            run.attempt_count = total_attempts
            db.session.commit()

            if round_index < max_rounds - 1 and delay_seconds > 0:
                time.sleep(delay_seconds)

        best_payloads_by_province = {}
        for province in province_geoids.keys():
            province_attempts = []
            for round_attempts in attempt_rounds:
                attempt = round_attempts.get(province)
                if attempt:
                    province_attempts.append(attempt)
            best = _pick_best_attempt(province_attempts)
            if best:
                best_attempt = best["attempt"]
                best_payloads_by_province[province] = {
                    "geo_id": best_attempt.get("geo_id"),
                    "url": best_attempt.get("url"),
                    "status_code": best_attempt.get("status_code"),
                    "payload": best_attempt.get("payload"),
                }

        if not best_payloads_by_province:
            run.status = "failed"
            all_errors = []
            for round_attempts in attempt_rounds:
                for province, attempt in round_attempts.items():
                    all_errors.append(f"{province}: {attempt.get('error') or 'respuesta invalida'}")
            run.error_message = "; ".join(all_errors)[:1200]
            run.finished_at_utc = datetime.utcnow()
            run.payload_json = json.dumps(
                {
                    "mode": "province_geoid_v1",
                    "provinces": {
                        province: {
                            "geo_id": attempt.get("geo_id"),
                            "ok": bool(attempt.get("ok")),
                            "status_code": attempt.get("status_code"),
                            "error": attempt.get("error"),
                        }
                        for round_attempts in attempt_rounds
                        for province, attempt in round_attempts.items()
                    },
                },
                ensure_ascii=False,
            )
            db.session.commit()
            raise RuntimeError(run.error_message or "No se pudo obtener datos de Radar")

        payload_record = {
            "mode": "province_geoid_v1",
            "generated_at_utc": serialize_snapshot_time(datetime.utcnow()),
            "provinces": {
                province: {
                    "geo_id": details.get("geo_id"),
                    "status_code": details.get("status_code"),
                    "url": details.get("url"),
                    "payload": details.get("payload"),
                }
                for province, details in best_payloads_by_province.items()
            },
        }

        snapshot, snapshot_error = _upsert_snapshot(run, best_payloads_by_province)
        if snapshot_error:
            run.status = "failed"
            run.error_message = snapshot_error
            run.finished_at_utc = datetime.utcnow()
            run.payload_json = json.dumps(payload_record, ensure_ascii=False)
            db.session.commit()
            raise RuntimeError(snapshot_error)

        run.status = "success"
        run.error_message = None
        run.finished_at_utc = datetime.utcnow()
        run.payload_json = json.dumps(payload_record, ensure_ascii=False)
        db.session.commit()

        print(
            "OK",
            json.dumps(
                {
                    "run_id": run.id,
                    "snapshot_id": snapshot.id,
                    "observed_at_utc": serialize_snapshot_time(snapshot.observed_at_utc),
                    "score": round(snapshot.score or 0, 2),
                    "status": snapshot.status,
                    "attempts": total_attempts,
                    "provinces_ok": len(best_payloads_by_province),
                },
                ensure_ascii=False,
            ),
        )


def main():
    args = parse_args()
    scheduled_for = _parse_scheduled_for(args.scheduled_for)
    run_ingestion(single_call=args.single_call, scheduled_for=scheduled_for)


if __name__ == "__main__":
    main()
