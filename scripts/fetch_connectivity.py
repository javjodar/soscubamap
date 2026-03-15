import argparse
import json
import os
import time
from datetime import datetime, timezone

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
from app.services.cuba_locations import PROVINCES
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


def _upsert_snapshot(run, payload):
    main_points = extract_series_points(payload, "main")
    previous_points = extract_series_points(payload, "previous")
    if not main_points:
        return None, "No se encontraron datapoints en la serie main"

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
        return None, "No fue posible calcular el score de conectividad"

    # Histeresis simple: evita cambios bruscos con variacion minima.
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
        method="national_replication_v1",
    )
    db.session.add(snapshot)
    db.session.flush()

    try:
        provinces = list_provinces() or list(PROVINCES)
    except Exception:
        provinces = list(PROVINCES)
    for province in provinces:
        db.session.add(
            ConnectivityProvinceStatus(
                snapshot_id=snapshot.id,
                province=province,
                score=score,
                status=status,
                confidence="estimated_country_level",
                method="national_replication_v1",
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

        run = ConnectivityIngestionRun(
            scheduled_for_utc=scheduled_for,
            started_at_utc=datetime.utcnow(),
            status="running",
            attempt_count=0,
            api_url=api_url,
        )
        db.session.add(run)
        db.session.commit()

        attempts = []
        max_calls = 1 if single_call else 2
        for call_index in range(max_calls):
            attempt = _fetch_once(api_url, token, timeout_seconds)
            attempts.append(attempt)
            run.attempt_count = len(attempts)
            db.session.commit()

            if call_index < max_calls - 1 and delay_seconds > 0:
                time.sleep(delay_seconds)

        best = _pick_best_attempt(attempts)
        if not best:
            run.status = "failed"
            run.error_message = "; ".join(
                [a.get("error") or "respuesta invalida" for a in attempts]
            )[:1200]
            run.finished_at_utc = datetime.utcnow()
            run.payload_json = json.dumps(
                {
                    "attempts": [
                        {
                            "ok": bool(a.get("ok")),
                            "status_code": a.get("status_code"),
                            "error": a.get("error"),
                        }
                        for a in attempts
                    ]
                },
                ensure_ascii=False,
            )
            db.session.commit()
            raise RuntimeError(run.error_message or "No se pudo obtener datos de Radar")

        selected_attempt = best["attempt"]
        payload = selected_attempt.get("payload") or {}

        snapshot, snapshot_error = _upsert_snapshot(run, payload)
        if snapshot_error:
            run.status = "failed"
            run.error_message = snapshot_error
            run.finished_at_utc = datetime.utcnow()
            run.payload_json = json.dumps(payload, ensure_ascii=False)
            db.session.commit()
            raise RuntimeError(snapshot_error)

        run.status = "success"
        run.error_message = None
        run.finished_at_utc = datetime.utcnow()
        run.payload_json = json.dumps(payload, ensure_ascii=False)
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
                    "attempts": len(attempts),
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
