import json
import os
import unicodedata

from app.services.cuba_locations import PROVINCES, MUNICIPALITIES


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

DEFAULT_MUNICIPALITY_KEYS = [
    "municipality",
    "municipio",
    "nombre_mun",
    "name",
    "NAME_2",
    "name_2",
    "ADM2_ES",
    "ADM2_NAME",
    "NAME_ES",
]

DEFAULT_MUNICIPALITY_PROVINCE_KEYS = [
    "province",
    "provincia",
    "provincia_nombre",
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


PROVINCE_CANONICAL = {_normalize(p): p for p in PROVINCES}
MUNICIPALITY_CANONICAL = {
    _normalize(m): m
    for province, muns in MUNICIPALITIES.items()
    for m in muns
}


_cache = {
    "provinces": None,
    "municipalities": None,
    "paths": {},
}


CUBA_LAT_MIN = 19.0
CUBA_LAT_MAX = 24.2
CUBA_LNG_MIN = -86.2
CUBA_LNG_MAX = -73.0


def _get_env_or_config(key, default=None):
    try:
        from flask import current_app

        return current_app.config.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


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


def _pick_name(props, keys):
    for key in keys:
        if key in props and props[key]:
            return props[key]
    return None


def _extract_polygons(geometry):
    if not geometry:
        return []
    if geometry.get("type") == "Polygon":
        return [geometry.get("coordinates", [])]
    if geometry.get("type") == "MultiPolygon":
        return geometry.get("coordinates", [])
    return []


def _load_features(path, keys, canonical_map, province_keys=None, province_canonical=None):
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    features = data.get("features", [])
    items = []
    for feature in features:
        geom = feature.get("geometry")
        polygons = _extract_polygons(geom)
        if not polygons:
            continue
        props = feature.get("properties", {}) or {}
        name = _pick_name(props, keys)
        if name:
            name_norm = _normalize(name)
            name = canonical_map.get(name_norm, str(name).strip())
        else:
            name = None
        province = None
        if province_keys:
            province_val = _pick_name(props, province_keys)
            if province_val:
                province_norm = _normalize(province_val)
                if province_canonical:
                    province = province_canonical.get(province_norm, str(province_val).strip())
                else:
                    province = str(province_val).strip()
        items.append({"name": name, "polygons": polygons, "province": province})
    return items


def _point_in_ring(point, ring):
    x, y = point
    if not ring:
        return False
    # Ensure ring closed
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    inside = False
    for i in range(len(ring) - 1):
        xi, yi = ring[i]
        xj, yj = ring[i + 1]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        )
        if intersects:
            inside = not inside
    return inside


def _point_in_polygon(point, polygon):
    if not polygon:
        return False
    outer = polygon[0]
    if not _point_in_ring(point, outer):
        return False
    # holes
    for hole in polygon[1:]:
        if _point_in_ring(point, hole):
            return False
    return True


def _contains(point, polygons):
    for polygon in polygons:
        if _point_in_polygon(point, polygon):
            return True
    return False


def _load_layers():
    prov_path = _resolve_path(_get_env_or_config("GEOJSON_PROVINCES_PATH"))
    mun_path = _resolve_path(_get_env_or_config("GEOJSON_MUNICIPALITIES_PATH"))

    prov_keys = _get_env_or_config("GEOJSON_PROVINCE_KEYS")
    mun_keys = _get_env_or_config("GEOJSON_MUNICIPALITY_KEYS")
    mun_prov_keys = _get_env_or_config("GEOJSON_MUNICIPALITY_PROVINCE_KEYS")

    prov_keys = [k.strip() for k in (prov_keys or "").split(",") if k.strip()] or DEFAULT_PROVINCE_KEYS
    mun_keys = [k.strip() for k in (mun_keys or "").split(",") if k.strip()] or DEFAULT_MUNICIPALITY_KEYS
    mun_prov_keys = [k.strip() for k in (mun_prov_keys or "").split(",") if k.strip()] or DEFAULT_MUNICIPALITY_PROVINCE_KEYS

    if _cache["paths"].get("provinces") != (prov_path, tuple(prov_keys)):
        _cache["provinces"] = _load_features(prov_path, prov_keys, PROVINCE_CANONICAL)
        _cache["paths"]["provinces"] = (prov_path, tuple(prov_keys))

    if _cache["paths"].get("municipalities") != (mun_path, tuple(mun_keys), tuple(mun_prov_keys)):
        _cache["municipalities"] = _load_features(
            mun_path,
            mun_keys,
            MUNICIPALITY_CANONICAL,
            province_keys=mun_prov_keys,
            province_canonical=PROVINCE_CANONICAL,
        )
        _cache["paths"]["municipalities"] = (mun_path, tuple(mun_keys), tuple(mun_prov_keys))


def lookup_location(lat, lng):
    _load_layers()
    point = (float(lng), float(lat))
    province = None
    municipality = None

    for item in _cache.get("provinces") or []:
        if _contains(point, item["polygons"]):
            province = item["name"]
            break

    for item in _cache.get("municipalities") or []:
        if _contains(point, item["polygons"]):
            municipality = item["name"]
            if not province and item.get("province"):
                province = item["province"]
            break

    return province, municipality


def list_provinces():
    _load_layers()
    items = [i["name"] for i in (_cache.get("provinces") or []) if i.get("name")]
    if items:
        return sorted(set(items))
    mun_map = municipalities_map()
    if mun_map:
        return sorted(mun_map.keys())
    return list(PROVINCES)


def list_municipalities(province=None):
    _load_layers()
    mun_map = municipalities_map()
    if province:
        return mun_map.get(province, [])
    all_muns = []
    for items in mun_map.values():
        all_muns.extend(items)
    return sorted(set(all_muns))


def municipalities_map():
    _load_layers()
    items = _cache.get("municipalities") or []
    mapping = {}
    for item in items:
        province = item.get("province")
        name = item.get("name")
        if not province or not name:
            continue
        mapping.setdefault(province, set()).add(name)
    if mapping:
        return {province: sorted(list(names)) for province, names in mapping.items()}
    return MUNICIPALITIES


def is_within_cuba_bounds(lat, lng):
    try:
        lat_value = float(lat)
        lng_value = float(lng)
    except Exception:
        return False
    return (
        CUBA_LAT_MIN <= lat_value <= CUBA_LAT_MAX
        and CUBA_LNG_MIN <= lng_value <= CUBA_LNG_MAX
    )
