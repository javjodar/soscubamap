from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone


STATUS_NORMAL = "normal"
STATUS_DEGRADED = "degraded"
STATUS_SEVERE = "severe"
STATUS_CRITICAL = "critical"
STATUS_UNKNOWN = "unknown"

STATUS_LABELS = {
    STATUS_NORMAL: "Normal",
    STATUS_DEGRADED: "Degradacion leve",
    STATUS_SEVERE: "Problemas severos",
    STATUS_CRITICAL: "Apagon o conectividad critica",
    STATUS_UNKNOWN: "Sin datos",
}

STATUS_COLORS = {
    STATUS_NORMAL: "#2E7D32",
    STATUS_DEGRADED: "#F9A825",
    STATUS_SEVERE: "#EF6C00",
    STATUS_CRITICAL: "#C62828",
    STATUS_UNKNOWN: "#667085",
}

# Ajuste operativo:
# >=50 verde, >=30 amarillo, >=15 naranja, <5 rojo.
# El rango 5-15 se mantiene en naranja para evitar huecos.
SCORE_GREEN_MIN = 50.0
SCORE_YELLOW_MIN = 30.0
SCORE_ORANGE_MIN = 15.0
SCORE_RED_MAX_EXCLUSIVE = 5.0

_TIMESTAMP_KEYS = (
    "timestamp",
    "timestamps",
    "time",
    "times",
    "date",
    "dates",
    "datetime",
    "datetimes",
)

_VALUE_KEYS = (
    "requests",
    "request",
    "value",
    "values",
    "traffic",
    "count",
    "total",
)


def utcnow_naive() -> datetime:
    return datetime.utcnow()


def parse_datetime_utc(raw):
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo:
            return raw.astimezone(timezone.utc).replace(tzinfo=None)
        return raw
    if isinstance(raw, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(raw))
        except Exception:
            return None

    text = str(raw).strip()
    if not text:
        return None

    # Soporta ISO8601 tipo 2026-03-14T12:00:00Z
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    for candidate in (text, text.replace(" ", "T")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            continue

    return None


def to_float(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        return value if math.isfinite(value) else None

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        parsed = float(text)
    except Exception:
        return None
    return parsed if math.isfinite(parsed) else None


def _best_numeric_list(series_dict, timestamps):
    preferred = []
    fallback = []
    ts_len = len(timestamps)

    for key, value in (series_dict or {}).items():
        if key in _TIMESTAMP_KEYS:
            continue
        if not isinstance(value, list) or len(value) != ts_len:
            continue
        numeric_values = [to_float(v) for v in value]
        if not any(v is not None for v in numeric_values):
            continue
        entry = (key, numeric_values)
        if key.lower() in _VALUE_KEYS:
            preferred.append(entry)
        else:
            fallback.append(entry)

    if preferred:
        return preferred[0]
    if fallback:
        return fallback[0]
    return (None, [])


def _extract_points_from_timestamps_object(series_dict):
    timestamps = None
    for key in _TIMESTAMP_KEYS:
        candidate = series_dict.get(key)
        if isinstance(candidate, list) and candidate:
            timestamps = candidate
            break

    if not timestamps:
        return []

    _metric_key, values = _best_numeric_list(series_dict, timestamps)
    points = []
    for idx, ts in enumerate(timestamps):
        dt = parse_datetime_utc(ts)
        value = values[idx] if idx < len(values) else None
        if dt is None or value is None:
            continue
        points.append({"timestamp": dt, "value": value})
    return points


def _extract_point_from_row(item):
    if not isinstance(item, dict):
        return None

    dt = None
    for key in _TIMESTAMP_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            continue
        parsed = parse_datetime_utc(value)
        if parsed is not None:
            dt = parsed
            break

    value = None
    for key in _VALUE_KEYS:
        if key in item:
            parsed = to_float(item.get(key))
            if parsed is not None:
                value = parsed
                break

    if value is None:
        for candidate in item.values():
            parsed = to_float(candidate)
            if parsed is not None:
                value = parsed
                break

    if dt is None or value is None:
        return None

    return {"timestamp": dt, "value": value}


def extract_timeseries_points(series):
    if not series:
        return []

    if isinstance(series, dict):
        points = _extract_points_from_timestamps_object(series)
        if points:
            return _sort_and_dedupe_points(points)

        for key in ("data", "series", "timeseries", "result", "values"):
            nested = series.get(key)
            nested_points = extract_timeseries_points(nested)
            if nested_points:
                return _sort_and_dedupe_points(nested_points)
        return []

    if isinstance(series, list):
        points = []
        for item in series:
            if isinstance(item, dict):
                row_point = _extract_point_from_row(item)
                if row_point:
                    points.append(row_point)
                    continue
                nested_points = extract_timeseries_points(item)
                if nested_points:
                    points.extend(nested_points)
        return _sort_and_dedupe_points(points)

    return []


def _sort_and_dedupe_points(points):
    latest_by_ts = {}
    for point in points:
        ts = point.get("timestamp")
        value = point.get("value")
        if not isinstance(ts, datetime):
            continue
        if value is None:
            continue
        latest_by_ts[ts] = value
    sorted_items = sorted(latest_by_ts.items(), key=lambda item: item[0])
    return [{"timestamp": ts, "value": value} for ts, value in sorted_items]


def _search_named_series(node, target_name):
    if node is None:
        return None

    if isinstance(node, dict):
        if target_name in node:
            return node[target_name]

        name_value = node.get("name")
        if isinstance(name_value, str) and name_value.lower() == target_name.lower():
            return node

        for value in node.values():
            found = _search_named_series(value, target_name)
            if found is not None:
                return found
        return None

    if isinstance(node, list):
        for item in node:
            found = _search_named_series(item, target_name)
            if found is not None:
                return found

    return None


def extract_series_points(payload, series_name):
    if not isinstance(payload, dict):
        return []
    result = payload.get("result", payload)

    series = None
    if isinstance(result, dict):
        series = result.get(series_name)
    if series is None:
        series = _search_named_series(result, series_name)
    if series is None and series_name == "main":
        series = result

    return extract_timeseries_points(series)


def get_latest_hourly_point(payload, series_name="main"):
    points = extract_series_points(payload, series_name)
    if not points:
        return None
    return points[-1]


def get_latest_common_point(main_points, previous_points):
    if not main_points or not previous_points:
        return None

    previous_map = {item["timestamp"]: item["value"] for item in previous_points}
    for item in reversed(main_points):
        ts = item.get("timestamp")
        if ts in previous_map:
            return {
                "timestamp": ts,
                "main_value": item.get("value"),
                "previous_value": previous_map.get(ts),
            }
    return None


def score_to_status(score):
    if score is None:
        return STATUS_UNKNOWN

    try:
        numeric = float(score)
    except Exception:
        return STATUS_UNKNOWN

    if numeric >= SCORE_GREEN_MIN:
        return STATUS_NORMAL
    if numeric >= SCORE_YELLOW_MIN:
        return STATUS_DEGRADED
    if numeric >= SCORE_ORANGE_MIN:
        return STATUS_SEVERE
    if numeric < SCORE_RED_MAX_EXCLUSIVE:
        return STATUS_CRITICAL
    return STATUS_SEVERE


def compute_connectivity_score(latest_value, baseline_value):
    latest = to_float(latest_value)
    baseline = to_float(baseline_value)

    if latest is None:
        return None, STATUS_UNKNOWN

    if baseline is None or baseline <= 0:
        score = 100.0
    else:
        score = (latest / baseline) * 100.0
        score = max(0.0, min(score, 100.0))

    return score, score_to_status(score)


def median_baseline(values):
    numeric = [to_float(v) for v in values or []]
    numeric = [v for v in numeric if v is not None and v > 0]
    if not numeric:
        return None
    return float(statistics.median(numeric))


def serialize_snapshot_time(dt):
    if not isinstance(dt, datetime):
        return None
    return dt.replace(microsecond=0).isoformat() + "Z"
