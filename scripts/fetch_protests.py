import argparse
import json
import time

import requests

from app import create_app
from app.extensions import db
from app.models.protest_event import ProtestEvent
from app.models.protest_ingestion_run import ProtestIngestionRun
from app.services.protests import (
    build_event_payload,
    get_fetch_interval_seconds,
    get_fetch_timeout_seconds,
    get_rss_feed_urls,
    parse_feed_payload,
    utcnow_naive,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Ingesta de protestas desde feeds RSS")
    parser.add_argument(
        "--feed",
        action="append",
        default=[],
        help="Feed RSS especifico. Se puede repetir para varios feeds.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Ejecuta ingesta continua con intervalo fijo.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help="Intervalo entre ingestas cuando se usa --loop (minimo 60).",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Cantidad maxima de ciclos cuando se usa --loop (0 = infinito).",
    )
    return parser.parse_args()


def _fetch_feed(url, timeout_seconds):
    headers = {
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        "User-Agent": "soscubamap-protest-ingestor/1.0",
    }
    response = requests.get(url, headers=headers, timeout=timeout_seconds)
    return {
        "ok": response.ok,
        "status_code": response.status_code,
        "text": response.text or "",
    }


def _find_existing_event(payload):
    source_url = (payload.get("source_url") or "").strip()
    source_feed = (payload.get("source_feed") or "").strip()
    source_guid = (payload.get("source_guid") or "").strip() or None
    dedupe_hash = (payload.get("dedupe_hash") or "").strip()

    if source_url:
        row = (
            ProtestEvent.query.filter(ProtestEvent.source_url == source_url)
            .order_by(ProtestEvent.id.desc())
            .first()
        )
        if row:
            return row

    if source_guid:
        row = (
            ProtestEvent.query.filter(
                ProtestEvent.source_feed == source_feed,
                ProtestEvent.source_guid == source_guid,
            )
            .order_by(ProtestEvent.id.desc())
            .first()
        )
        if row:
            return row

    if dedupe_hash:
        row = (
            ProtestEvent.query.filter(ProtestEvent.dedupe_hash == dedupe_hash)
            .order_by(ProtestEvent.id.desc())
            .first()
        )
        if row:
            return row

    return None


def _upsert_event(payload):
    payload = dict(payload or {})
    payload["source_guid"] = (payload.get("source_guid") or "").strip() or None
    payload["related_group_hash"] = payload.get("dedupe_hash")
    now = utcnow_naive()

    existing = _find_existing_event(payload)
    if existing:
        changed = False
        manual_locked = (existing.review_status or "").strip().lower() in {
            "approved_manual",
            "hidden_manual",
        }
        updatable_fields = [
            "source_feed",
            "source_name",
            "source_guid",
            "source_url",
            "source_platform",
            "source_author",
            "source_published_at_utc",
            "published_day_utc",
            "raw_title",
            "raw_description",
            "clean_text",
            "detected_keywords_json",
            "matched_place_text",
            "matched_feature_type",
            "matched_feature_name",
            "matched_province",
            "matched_municipality",
            "matched_locality",
            "latitude",
            "longitude",
            "location_precision",
            "confidence_score",
            "event_type",
            "review_status",
            "visible_on_map",
            "dedupe_hash",
            "related_group_hash",
            "transparency_note",
        ]
        for field in updatable_fields:
            if manual_locked and field in {"review_status", "visible_on_map"}:
                # Respeta la decisión manual del admin aunque cambie la heurística automática.
                continue
            new_value = payload.get(field)
            if getattr(existing, field) != new_value:
                setattr(existing, field, new_value)
                changed = True
        if changed:
            existing.updated_at = now
            return "updated", existing
        return "deduped", existing

    payload["created_at"] = now
    payload["updated_at"] = now
    event = ProtestEvent(**payload)
    db.session.add(event)
    return "stored", event


def run_ingestion(feeds):
    app = create_app()
    with app.app_context():
        feed_urls = [url.strip() for url in feeds if url and url.strip()]
        if not feed_urls:
            feed_urls = get_rss_feed_urls()
        if not feed_urls:
            raise RuntimeError("No hay feeds RSS configurados en PROTEST_RSS_FEEDS_JSON_PATH")

        timeout_seconds = get_fetch_timeout_seconds()
        run = ProtestIngestionRun(
            started_at_utc=utcnow_naive(),
            status="running",
            feed_count=len(feed_urls),
        )
        db.session.add(run)
        db.session.commit()

        summary = {
            "feeds": {},
            "errors": [],
        }
        fetched_items = 0
        parsed_items = 0
        stored_items = 0
        updated_items = 0
        deduped_items = 0
        hidden_items = 0

        try:
            for feed_url in feed_urls:
                feed_entry = {
                    "status": "pending",
                    "http_status": None,
                    "items": 0,
                    "parsed": 0,
                    "stored": 0,
                    "updated": 0,
                    "deduped": 0,
                    "hidden": 0,
                    "error": None,
                }
                summary["feeds"][feed_url] = feed_entry

                try:
                    response = _fetch_feed(feed_url, timeout_seconds)
                    feed_entry["http_status"] = response.get("status_code")
                    if not response.get("ok"):
                        feed_entry["status"] = "failed"
                        feed_entry["error"] = f"HTTP {response.get('status_code')}"
                        summary["errors"].append(f"{feed_url}: {feed_entry['error']}")
                        continue

                    raw_items = parse_feed_payload(response.get("text"), feed_url)
                    fetched_items += len(raw_items)
                    feed_entry["items"] = len(raw_items)
                    feed_entry["parsed"] = len(raw_items)
                    parsed_items += len(raw_items)

                    for item in raw_items:
                        payload = build_event_payload(item)
                        state, event = _upsert_event(payload)
                        if state == "stored":
                            stored_items += 1
                            feed_entry["stored"] += 1
                        elif state == "updated":
                            updated_items += 1
                            feed_entry["updated"] += 1
                        else:
                            deduped_items += 1
                            feed_entry["deduped"] += 1

                        if not event.visible_on_map:
                            hidden_items += 1
                            feed_entry["hidden"] += 1

                    feed_entry["status"] = "ok"
                except Exception as exc:
                    feed_entry["status"] = "failed"
                    feed_entry["error"] = str(exc)
                    summary["errors"].append(f"{feed_url}: {exc}")

            run.fetched_items = fetched_items
            run.parsed_items = parsed_items
            run.stored_items = stored_items
            run.updated_items = updated_items
            run.deduped_items = deduped_items
            run.hidden_items = hidden_items
            run.payload_json = json.dumps(summary, ensure_ascii=False)
            run.finished_at_utc = utcnow_naive()
            run.status = "failed" if len(summary["errors"]) == len(feed_urls) else "success"
            run.error_message = "; ".join(summary["errors"])[:1200] if summary["errors"] else None

            db.session.commit()
            print(
                "OK",
                json.dumps(
                    {
                        "run_id": run.id,
                        "status": run.status,
                        "feeds": len(feed_urls),
                        "fetched_items": fetched_items,
                        "parsed_items": parsed_items,
                        "stored_items": stored_items,
                        "updated_items": updated_items,
                        "deduped_items": deduped_items,
                        "hidden_items": hidden_items,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception:
            db.session.rollback()
            run.status = "failed"
            run.finished_at_utc = utcnow_naive()
            run.error_message = "Fallo inesperado durante la ingesta de protestas"
            run.payload_json = json.dumps(summary, ensure_ascii=False)
            db.session.commit()
            raise


def run_scheduler(feeds, interval_seconds=None, max_runs=0):
    interval = max(60, int(interval_seconds or get_fetch_interval_seconds()))
    run_count = 0
    print(
        "SCHEDULER",
        json.dumps(
            {
                "interval_seconds": interval,
                "max_runs": int(max_runs or 0),
                "mode": "loop",
            },
            ensure_ascii=False,
        ),
    )
    while True:
        run_count += 1
        started = time.monotonic()
        try:
            run_ingestion(feeds)
        except Exception as exc:
            print(
                "ERROR",
                json.dumps(
                    {
                        "run_number": run_count,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                ),
            )

        if max_runs and run_count >= int(max_runs):
            break

        elapsed = time.monotonic() - started
        sleep_seconds = max(5, int(interval - elapsed))
        print(
            "SLEEP",
            json.dumps(
                {
                    "run_number": run_count,
                    "sleep_seconds": sleep_seconds,
                },
                ensure_ascii=False,
            ),
        )
        time.sleep(sleep_seconds)


def main():
    args = parse_args()
    if args.loop:
        run_scheduler(
            args.feed or [],
            interval_seconds=args.interval_seconds,
            max_runs=args.max_runs,
        )
        return
    run_ingestion(args.feed or [])


if __name__ == "__main__":
    main()
