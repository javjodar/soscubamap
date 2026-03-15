import copy
import json
import os
import unicodedata

from app.services.cuba_locations import PROVINCES

DEFAULT_PROVINCE_KEYS = [
    "province",
    "provincia",
    "nombre_prov",
    "name",
    "shapeName",
    "shape_name",
    "NAME_1",
    "name_1",
    "ADM1_ES",
    "ADM1_NAME",
    "NAME_ES",
]


def _normalize(value):
    if not value:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


PROVINCE_CANONICAL = {_normalize(name): name for name in PROVINCES}

_CACHE = {
    "signature": None,
    "geojson": None,
}


def _get_env_or_config(key, default=None):
    try:
        from flask import current_app

        return current_app.config.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def _pick_province_name(properties, keys):
    if not isinstance(properties, dict):
        return None
    for key in keys:
        value = properties.get(key)
        if value:
            return str(value).strip()
    return None


def _is_polygon_geometry(geometry):
    if not isinstance(geometry, dict):
        return False
    return geometry.get("type") in {"Polygon", "MultiPolygon"}


def _configured_keys():
    raw = _get_env_or_config("GEOJSON_PROVINCE_KEYS", "") or ""
    keys = [item.strip() for item in raw.split(",") if item.strip()]
    return keys or DEFAULT_PROVINCE_KEYS


def _resolve_path(path):
    raw = (path or "").strip()
    if not raw:
        return ""

    expanded = os.path.expanduser(os.path.expandvars(raw))
    if os.path.isabs(expanded):
        return expanded

    candidates = []
    try:
        from flask import current_app

        project_root = os.path.abspath(os.path.join(current_app.root_path, os.pardir))
        candidates.append(os.path.abspath(os.path.join(project_root, expanded)))
    except Exception:
        pass

    candidates.append(os.path.abspath(expanded))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return candidates[0]


def _load_geojson_from_disk(path, keys):
    if not path or not os.path.exists(path):
        return {"type": "FeatureCollection", "features": []}

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    features = data.get("features") or []
    normalized_features = []

    for feature in features:
        if not isinstance(feature, dict):
            continue

        geometry = feature.get("geometry")
        if not _is_polygon_geometry(geometry):
            continue

        props = feature.get("properties") or {}
        raw_name = _pick_province_name(props, keys)
        if not raw_name:
            continue

        canonical = PROVINCE_CANONICAL.get(_normalize(raw_name), raw_name)

        normalized_features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "province": canonical,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": normalized_features,
    }


def load_province_geojson():
    configured_path = _get_env_or_config("GEOJSON_PROVINCES_PATH", "")
    path = _resolve_path(configured_path)
    keys = _configured_keys()

    signature = (configured_path, path, tuple(keys))
    if _CACHE["signature"] != signature:
        _CACHE["geojson"] = _load_geojson_from_disk(path, keys)
        _CACHE["signature"] = signature

    return copy.deepcopy(_CACHE["geojson"]) if _CACHE["geojson"] else {"type": "FeatureCollection", "features": []}


def province_names_from_geojson(geojson):
    if not isinstance(geojson, dict):
        return []
    names = []
    for feature in geojson.get("features") or []:
        name = (feature.get("properties") or {}).get("province")
        if name:
            names.append(name)
    return sorted(set(names))


def enrich_geojson_with_status(geojson, status_by_province):
    payload = copy.deepcopy(geojson or {"type": "FeatureCollection", "features": []})
    for feature in payload.get("features") or []:
        props = feature.setdefault("properties", {})
        province = props.get("province")
        state = (status_by_province or {}).get(province) or {}
        props.update(
            {
                "score": state.get("score"),
                "status": state.get("status", "unknown"),
                "status_label": state.get("status_label", "Sin datos"),
                "status_color": state.get("status_color", "#667085"),
                "confidence": state.get("confidence", "unknown"),
                "is_estimated": state.get("is_estimated", True),
            }
        )
    return payload
