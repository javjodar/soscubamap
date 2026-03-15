import hashlib
import html
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree

import bleach

from app.services.cuba_locations import MUNICIPALITIES, PROVINCES

DEFAULT_STRONG_KEYWORDS = [
    "protesta",
    "protestas",
    "manifestantes",
    "cacerolazo",
    "cacerolas",
    "calderos",
    "trancar calles",
    "trancan calles",
    "gritar libertad",
    "toma de la sede",
]

DEFAULT_CONTEXT_KEYWORDS = [
    "detenidos",
    "represion",
    "represion policial",
    "disparo",
    "herido",
    "incendiaron",
    "incendian",
    "descontento social",
    "indignacion popular",
    "calle tomada",
]

DEFAULT_WEAK_KEYWORDS = [
    "situacion",
    "movilizacion",
    "regimen",
    "seguimiento",
]

DEFAULT_LOCALITY_KEYS = [
    "locality",
    "localidad",
    "name",
    "NAME_3",
    "name_3",
    "shapeName",
    "barrio",
    "asentamiento",
]

DEFAULT_LOCALITY_MUNICIPALITY_KEYS = [
    "municipality",
    "municipio",
    "NAME_2",
    "name_2",
    "ADM2_ES",
    "ADM2_NAME",
]

DEFAULT_LOCALITY_PROVINCE_KEYS = [
    "province",
    "provincia",
    "NAME_1",
    "name_1",
    "ADM1_ES",
    "ADM1_NAME",
]

DEFAULT_PROVINCE_KEYS = [
    "province",
    "provincia",
    "name",
    "shapeName",
    "NAME_1",
    "name_1",
]

DEFAULT_MUNICIPALITY_KEYS = [
    "municipality",
    "municipio",
    "name",
    "NAME_2",
    "name_2",
]

DEFAULT_MUNICIPALITY_PROVINCE_KEYS = [
    "province",
    "provincia",
    "NAME_1",
    "name_1",
]

GENERIC_PLACE_TERMS = {"cuba", "la isla", "pais", "todo el pais"}

_GAZETTEER_CACHE = {
    "signature": None,
    "data": None,
}


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_env_or_config(key, default=None):
    try:
        from flask import current_app

        return current_app.config.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _safe_slug(value):
    text = _normalize_text(value)
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _csv_env_list(value, defaults=None):
    raw = str(value or "").strip()
    if not raw:
        return list(defaults or [])
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or list(defaults or [])


def get_rss_feed_urls():
    raw = _get_env_or_config("PROTEST_RSS_FEEDS", "")
    return _csv_env_list(raw)


def get_fetch_timeout_seconds():
    raw = _get_env_or_config("PROTEST_FETCH_TIMEOUT_SECONDS", "30")
    try:
        return max(5, int(raw))
    except Exception:
        return 30


def get_frontend_refresh_seconds():
    raw = _get_env_or_config("PROTEST_FRONTEND_REFRESH_SECONDS", "300")
    try:
        return max(30, int(raw))
    except Exception:
        return 300


def get_min_confidence_to_show():
    raw = _get_env_or_config("PROTEST_MIN_CONFIDENCE_TO_SHOW", "35")
    try:
        return max(0.0, min(100.0, float(raw)))
    except Exception:
        return 35.0


def require_source_url_for_map():
    raw = _get_env_or_config("PROTEST_REQUIRE_SOURCE_URL", "1")
    return _truthy(raw)


def allow_unresolved_location_on_map():
    raw = _get_env_or_config("PROTEST_ALLOW_UNRESOLVED_TO_MAP", "0")
    return _truthy(raw)


def get_max_items_per_feed():
    raw = _get_env_or_config("PROTEST_MAX_ITEMS_PER_FEED", "120")
    try:
        return max(1, int(raw))
    except Exception:
        return 120


def get_max_post_age_days():
    raw = _get_env_or_config("PROTEST_MAX_POST_AGE_DAYS", "30")
    try:
        return max(1, int(raw))
    except Exception:
        return 30


def get_protest_keyword_sets():
    strong = _csv_env_list(
        _get_env_or_config("PROTEST_KEYWORDS_STRONG", ""),
        defaults=DEFAULT_STRONG_KEYWORDS,
    )
    context = _csv_env_list(
        _get_env_or_config("PROTEST_KEYWORDS_CONTEXT", ""),
        defaults=DEFAULT_CONTEXT_KEYWORDS,
    )
    weak = _csv_env_list(
        _get_env_or_config("PROTEST_KEYWORDS_WEAK", ""),
        defaults=DEFAULT_WEAK_KEYWORDS,
    )
    return {
        "strong": sorted({_normalize_text(item) for item in strong if item}),
        "context": sorted({_normalize_text(item) for item in context if item}),
        "weak": sorted({_normalize_text(item) for item in weak if item}),
    }


def clean_description_html(raw_html):
    text = bleach.clean(str(raw_html or ""), tags=[], attributes={}, strip=True)
    text = html.unescape(text)
    return " ".join(text.split())


def canonicalize_source_url(raw_url):
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return ""
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_"):
            continue
        if key_lower in {"fbclid", "gclid", "ref", "ref_src", "source"}:
            continue
        query.append((key, value))
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=urlencode(query, doseq=True),
        fragment="",
    )
    return urlunparse(normalized)


def _strip_tag_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _child_text(item, tag_name):
    if item is None:
        return ""
    for child in list(item):
        if _strip_tag_name(child.tag) == tag_name:
            return (child.text or "").strip()
    return ""


def parse_rss_datetime(raw_value):
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def parse_rss_items(xml_text, source_feed):
    feed_url = str(source_feed or "").strip()
    if not str(xml_text or "").strip():
        return []
    root = ElementTree.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        # Some feeds may emit Atom-like roots with item descendants.
        channel = root

    items = []
    for item in channel.iter():
        if _strip_tag_name(item.tag) != "item":
            continue
        title = _child_text(item, "title")
        description_html = _child_text(item, "description")
        clean_description = clean_description_html(description_html)
        link = canonicalize_source_url(_child_text(item, "link"))
        guid = (_child_text(item, "guid") or "").strip()
        pub_date = parse_rss_datetime(_child_text(item, "pubDate"))
        merged_text = " ".join(part for part in [title, clean_description] if part).strip()
        if not merged_text:
            continue
        items.append(
            {
                "source_feed": feed_url,
                "title": title,
                "raw_description": description_html,
                "clean_description": clean_description,
                "clean_text": merged_text,
                "link": link,
                "guid": guid,
                "published_at_utc": pub_date,
            }
        )
    return items


def extract_source_name(feed_url):
    parsed = urlparse(str(feed_url or "").strip())
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "rss"


def _source_name_overrides():
    raw = str(_get_env_or_config("PROTEST_SOURCE_NAME_OVERRIDES_JSON", "") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}

    overrides = {}
    for raw_key, raw_name in payload.items():
        name = str(raw_name or "").strip()
        key = str(raw_key or "").strip()
        if not name or not key:
            continue
        canonical_key = canonicalize_source_url(key) or key
        overrides[canonical_key] = name
    return overrides


def _extract_handle_from_source_url(source_url):
    parsed = urlparse(str(source_url or "").strip())
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in {"x.com", "twitter.com"}:
        return ""

    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return ""
    first = segments[0].strip()
    if first.startswith("@"):
        first = first[1:]
    if first.lower() in {
        "i",
        "intent",
        "search",
        "hashtag",
        "home",
        "explore",
        "messages",
        "notifications",
        "compose",
        "settings",
    }:
        return ""
    if not re.match(r"^[A-Za-z0-9_]{1,30}$", first):
        return ""
    return f"@{first}"


def display_source_name(source_feed="", source_url="", fallback_name=""):
    overrides = _source_name_overrides()
    feed_key = canonicalize_source_url(source_feed) or str(source_feed or "").strip()
    source_key = canonicalize_source_url(source_url) or str(source_url or "").strip()

    if feed_key and feed_key in overrides:
        return overrides[feed_key]
    if source_key and source_key in overrides:
        return overrides[source_key]

    handle = _extract_handle_from_source_url(source_url)
    if handle:
        return handle

    fallback = str(fallback_name or "").strip()
    if fallback:
        return fallback
    if source_url:
        return extract_source_name(source_url)
    return extract_source_name(source_feed)


def extract_source_platform(source_url):
    host = extract_source_name(source_url)
    if host.endswith("x.com") or host.endswith("twitter.com"):
        return "x"
    if host.endswith("facebook.com"):
        return "facebook"
    if host.endswith("instagram.com"):
        return "instagram"
    if host.endswith("telegram.me") or host.endswith("t.me"):
        return "telegram"
    return "web"


def _extract_polygons(geometry):
    if not isinstance(geometry, dict):
        return []
    gtype = geometry.get("type")
    if gtype == "Polygon":
        return geometry.get("coordinates") or []
    if gtype == "MultiPolygon":
        polygons = geometry.get("coordinates") or []
        points = []
        for polygon in polygons:
            if polygon:
                points.extend(polygon[0])
        return [points]
    return []


def _geometry_centroid(geometry):
    rings = _extract_polygons(geometry)
    if not rings:
        return None, None
    points = []
    for ring in rings:
        if not ring:
            continue
        if isinstance(ring[0], (float, int)):
            # Already flattened point list.
            continue
        points.extend(ring)
    if not points:
        # Fallback when _extract_polygons returned flattened points for multipolygon.
        for ring in rings:
            if ring and isinstance(ring[0], (list, tuple)) and len(ring[0]) >= 2:
                points.extend(ring)
    if not points:
        return None, None
    lons = [float(point[0]) for point in points if len(point) >= 2]
    lats = [float(point[1]) for point in points if len(point) >= 2]
    if not lons or not lats:
        return None, None
    return (min(lats) + max(lats)) / 2.0, (min(lons) + max(lons)) / 2.0


def _resolve_path(raw_path):
    text = str(raw_path or "").strip()
    if not text:
        return ""
    expanded = os.path.expanduser(os.path.expandvars(text))
    if os.path.isabs(expanded):
        return expanded
    try:
        from flask import current_app

        project_root = os.path.abspath(os.path.join(current_app.root_path, os.pardir))
        candidate = os.path.abspath(os.path.join(project_root, expanded))
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    return os.path.abspath(expanded)


def _pick_name(props, keys):
    if not isinstance(props, dict):
        return ""
    for key in keys:
        value = props.get(key)
        if value:
            return str(value).strip()
    return ""


def _load_geojson(path):
    resolved = _resolve_path(path)
    if not resolved or not os.path.exists(resolved):
        return {"type": "FeatureCollection", "features": []}
    with open(resolved, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _add_entry(target, entry):
    term_key = _normalize_text(entry.get("name"))
    if not term_key:
        return
    bucket = target.setdefault(term_key, [])
    bucket.append(entry)


def _parse_aliases():
    raw = str(_get_env_or_config("PROTEST_PLACE_ALIASES_JSON", "") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    aliases = {}
    for alias, target in payload.items():
        alias_norm = _normalize_text(alias)
        target_norm = _normalize_text(target)
        if alias_norm and target_norm:
            aliases[alias_norm] = target_norm
    return aliases


def _build_gazetteer():
    province_geojson_path = _get_env_or_config("GEOJSON_PROVINCES_PATH", "")
    municipality_geojson_path = _get_env_or_config("GEOJSON_MUNICIPALITIES_PATH", "")
    locality_geojson_path = _get_env_or_config("GEOJSON_LOCALITIES_PATH", "")

    province_keys = _csv_env_list(
        _get_env_or_config("GEOJSON_PROVINCE_KEYS", ""),
        defaults=DEFAULT_PROVINCE_KEYS,
    )
    municipality_keys = _csv_env_list(
        _get_env_or_config("GEOJSON_MUNICIPALITY_KEYS", ""),
        defaults=DEFAULT_MUNICIPALITY_KEYS,
    )
    municipality_province_keys = _csv_env_list(
        _get_env_or_config("GEOJSON_MUNICIPALITY_PROVINCE_KEYS", ""),
        defaults=DEFAULT_MUNICIPALITY_PROVINCE_KEYS,
    )
    locality_keys = _csv_env_list(
        _get_env_or_config("GEOJSON_LOCALITY_KEYS", ""),
        defaults=DEFAULT_LOCALITY_KEYS,
    )
    locality_municipality_keys = _csv_env_list(
        _get_env_or_config("GEOJSON_LOCALITY_MUNICIPALITY_KEYS", ""),
        defaults=DEFAULT_LOCALITY_MUNICIPALITY_KEYS,
    )
    locality_province_keys = _csv_env_list(
        _get_env_or_config("GEOJSON_LOCALITY_PROVINCE_KEYS", ""),
        defaults=DEFAULT_LOCALITY_PROVINCE_KEYS,
    )

    provinces_idx = {}
    municipalities_idx = {}
    localities_idx = {}

    province_centroids = {}
    municipality_centroids = {}

    province_geojson = _load_geojson(province_geojson_path)
    for feature in province_geojson.get("features") or []:
        props = feature.get("properties") or {}
        name = _pick_name(props, province_keys)
        if not name:
            continue
        lat, lng = _geometry_centroid(feature.get("geometry"))
        province_name = name
        key = _normalize_text(province_name)
        if not key:
            continue
        province_centroids[key] = (lat, lng)
        _add_entry(
            provinces_idx,
            {
                "type": "province",
                "name": province_name,
                "province": province_name,
                "municipality": None,
                "locality": None,
                "lat": lat,
                "lng": lng,
            },
        )

    for province_name in PROVINCES:
        key = _normalize_text(province_name)
        lat, lng = province_centroids.get(key, (None, None))
        _add_entry(
            provinces_idx,
            {
                "type": "province",
                "name": province_name,
                "province": province_name,
                "municipality": None,
                "locality": None,
                "lat": lat,
                "lng": lng,
            },
        )

    municipality_geojson = _load_geojson(municipality_geojson_path)
    for feature in municipality_geojson.get("features") or []:
        props = feature.get("properties") or {}
        name = _pick_name(props, municipality_keys)
        if not name:
            continue
        province_name = _pick_name(props, municipality_province_keys)
        province_norm = _normalize_text(province_name)
        if not province_name:
            province_name = None
        lat, lng = _geometry_centroid(feature.get("geometry"))
        key = _normalize_text(name)
        if key:
            municipality_centroids[(key, province_norm)] = (lat, lng)
        _add_entry(
            municipalities_idx,
            {
                "type": "municipality",
                "name": name,
                "province": province_name,
                "municipality": name,
                "locality": None,
                "lat": lat,
                "lng": lng,
            },
        )

    for province_name, mun_list in MUNICIPALITIES.items():
        province_norm = _normalize_text(province_name)
        province_lat, province_lng = province_centroids.get(province_norm, (None, None))
        for municipality_name in mun_list:
            mun_norm = _normalize_text(municipality_name)
            lat, lng = municipality_centroids.get((mun_norm, province_norm), (None, None))
            if lat is None or lng is None:
                lat, lng = province_lat, province_lng
            _add_entry(
                municipalities_idx,
                {
                    "type": "municipality",
                    "name": municipality_name,
                    "province": province_name,
                    "municipality": municipality_name,
                    "locality": None,
                    "lat": lat,
                    "lng": lng,
                },
            )

    locality_geojson = _load_geojson(locality_geojson_path)
    for feature in locality_geojson.get("features") or []:
        props = feature.get("properties") or {}
        locality_name = _pick_name(props, locality_keys)
        if not locality_name:
            continue
        municipality_name = _pick_name(props, locality_municipality_keys)
        province_name = _pick_name(props, locality_province_keys)
        lat, lng = _geometry_centroid(feature.get("geometry"))
        province_norm = _normalize_text(province_name)
        municipality_norm = _normalize_text(municipality_name)
        if (lat is None or lng is None) and municipality_name:
            lat, lng = municipality_centroids.get((municipality_norm, province_norm), (None, None))
        if (lat is None or lng is None) and province_name:
            lat, lng = province_centroids.get(province_norm, (None, None))
        _add_entry(
            localities_idx,
            {
                "type": "locality",
                "name": locality_name,
                "province": province_name or None,
                "municipality": municipality_name or None,
                "locality": locality_name,
                "lat": lat,
                "lng": lng,
            },
        )

    all_idx = {}
    for idx in (localities_idx, municipalities_idx, provinces_idx):
        for key, entries in idx.items():
            all_idx.setdefault(key, []).extend(entries)

    aliases = _parse_aliases()
    for alias_key, target_key in aliases.items():
        if target_key in all_idx:
            all_idx.setdefault(alias_key, []).extend(all_idx[target_key])

    terms_sorted = sorted(all_idx.keys(), key=lambda item: len(item), reverse=True)
    return {
        "all": all_idx,
        "terms_sorted": terms_sorted,
        "province_terms": set(provinces_idx.keys()),
        "locality_terms": set(localities_idx.keys()),
        "municipality_terms": set(municipalities_idx.keys()),
    }


def _gazetteer():
    signature = (
        _get_env_or_config("GEOJSON_PROVINCES_PATH", ""),
        _get_env_or_config("GEOJSON_MUNICIPALITIES_PATH", ""),
        _get_env_or_config("GEOJSON_LOCALITIES_PATH", ""),
        _get_env_or_config("GEOJSON_PROVINCE_KEYS", ""),
        _get_env_or_config("GEOJSON_MUNICIPALITY_KEYS", ""),
        _get_env_or_config("GEOJSON_MUNICIPALITY_PROVINCE_KEYS", ""),
        _get_env_or_config("GEOJSON_LOCALITY_KEYS", ""),
        _get_env_or_config("GEOJSON_LOCALITY_MUNICIPALITY_KEYS", ""),
        _get_env_or_config("GEOJSON_LOCALITY_PROVINCE_KEYS", ""),
        _get_env_or_config("PROTEST_PLACE_ALIASES_JSON", ""),
    )
    if _GAZETTEER_CACHE["signature"] != signature:
        _GAZETTEER_CACHE["signature"] = signature
        _GAZETTEER_CACHE["data"] = _build_gazetteer()
    return _GAZETTEER_CACHE["data"] or {"all": {}, "terms_sorted": []}


def _find_terms_in_text(normalized_text, terms):
    found = []
    for term in terms:
        if not term:
            continue
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized_text):
            found.append(term)
    return found


def detect_keywords(clean_text):
    normalized = _normalize_text(clean_text)
    keyword_sets = get_protest_keyword_sets()
    strong = _find_terms_in_text(normalized, keyword_sets["strong"])
    context = _find_terms_in_text(normalized, keyword_sets["context"])
    weak = _find_terms_in_text(normalized, keyword_sets["weak"])
    return {
        "strong": strong,
        "context": context,
        "weak": weak,
    }


def _candidate_specificity(entry):
    etype = (entry or {}).get("type")
    if etype == "locality":
        return 30
    if etype == "municipality":
        return 20
    if etype == "province":
        return 10
    return 0


def resolve_place(clean_text):
    normalized = _normalize_text(clean_text)
    if not normalized:
        return {
            "resolved": False,
            "matched_place_text": "",
            "feature_type": None,
            "feature_name": None,
            "province": None,
            "municipality": None,
            "locality": None,
            "latitude": None,
            "longitude": None,
            "location_precision": "unresolved",
            "ambiguity": False,
        }

    if normalized in GENERIC_PLACE_TERMS:
        return {
            "resolved": False,
            "matched_place_text": normalized,
            "feature_type": None,
            "feature_name": None,
            "province": None,
            "municipality": None,
            "locality": None,
            "latitude": None,
            "longitude": None,
            "location_precision": "unresolved",
            "ambiguity": False,
        }

    gazetteer = _gazetteer()
    all_idx = gazetteer.get("all") or {}
    terms_sorted = gazetteer.get("terms_sorted") or []
    province_terms = gazetteer.get("province_terms") or set()

    context_provinces = set()
    for term in terms_sorted:
        if term not in province_terms:
            continue
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized):
            context_provinces.add(term)

    candidates = []
    for term in terms_sorted:
        if term in GENERIC_PLACE_TERMS:
            continue
        if not re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized):
            continue
        for entry in all_idx.get(term, []):
            province_norm = _normalize_text(entry.get("province"))
            score = _candidate_specificity(entry) + len(term) / 12.0
            if province_norm and province_norm in context_provinces:
                score += 8.0
            if "," in normalized and term in normalized:
                score += 1.0
            candidates.append((score, term, entry))

    if not candidates:
        return {
            "resolved": False,
            "matched_place_text": "",
            "feature_type": None,
            "feature_name": None,
            "province": None,
            "municipality": None,
            "locality": None,
            "latitude": None,
            "longitude": None,
            "location_precision": "unresolved",
            "ambiguity": False,
        }

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_term, best_entry = candidates[0]
    ambiguity = False
    if len(candidates) > 1:
        second_score, second_term, second_entry = candidates[1]
        if abs(best_score - second_score) < 0.8 and best_term == second_term:
            best_province = _normalize_text(best_entry.get("province"))
            second_province = _normalize_text(second_entry.get("province"))
            if best_province != second_province:
                ambiguity = True

    if ambiguity:
        return {
            "resolved": False,
            "matched_place_text": best_term,
            "feature_type": None,
            "feature_name": None,
            "province": None,
            "municipality": None,
            "locality": None,
            "latitude": None,
            "longitude": None,
            "location_precision": "unresolved",
            "ambiguity": True,
        }

    lat = best_entry.get("lat")
    lng = best_entry.get("lng")
    feature_type = best_entry.get("type")
    precision = "unresolved"
    if feature_type == "locality":
        precision = "exact_locality" if lat is not None and lng is not None else "approx_locality"
    elif feature_type == "municipality":
        precision = (
            "exact_municipality" if lat is not None and lng is not None else "approx_municipality"
        )
    elif feature_type == "province":
        precision = "exact_province" if lat is not None and lng is not None else "approx_province"

    return {
        "resolved": lat is not None and lng is not None,
        "matched_place_text": best_term,
        "feature_type": feature_type,
        "feature_name": best_entry.get("name"),
        "province": best_entry.get("province"),
        "municipality": best_entry.get("municipality"),
        "locality": best_entry.get("locality"),
        "latitude": lat,
        "longitude": lng,
        "location_precision": precision,
        "ambiguity": False,
    }


def classify_event(clean_text, keyword_hits, place_result):
    strong_count = len(keyword_hits.get("strong") or [])
    context_count = len(keyword_hits.get("context") or [])
    weak_count = len(keyword_hits.get("weak") or [])
    has_location = bool(place_result and place_result.get("resolved"))

    score = strong_count * 24 + context_count * 12 + weak_count * 5
    if has_location:
        score += 16
    if strong_count and context_count:
        score += 8
    if "cacerolas" in (keyword_hits.get("strong") or []) and "libertad" in _normalize_text(clean_text):
        score += 6
    if not has_location:
        score -= 10
    score = max(0.0, min(100.0, float(score)))

    if strong_count >= 2 and has_location:
        event_type = "confirmed_protest"
    elif strong_count >= 1 and has_location:
        event_type = "probable_protest"
    elif (strong_count >= 1 or context_count >= 2) and not has_location:
        event_type = "unresolved_location"
    elif context_count >= 1 and has_location:
        event_type = "related_unrest"
    else:
        event_type = "context_only"

    return score, event_type


def build_dedupe_hash(clean_text, source_url, published_at_utc, place_result):
    day_key = ""
    if isinstance(published_at_utc, datetime):
        day_key = published_at_utc.strftime("%Y-%m-%d")
    place_key = _normalize_text((place_result or {}).get("feature_name") or "")
    source_key = canonicalize_source_url(source_url)
    text_key = _normalize_text(re.sub(r"https?://\S+", "", clean_text or ""))
    seed = "|".join([source_key, day_key, place_key, text_key[:220]])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def should_show_on_map(event_payload):
    min_conf = get_min_confidence_to_show()
    require_source = require_source_url_for_map()
    allow_unresolved = allow_unresolved_location_on_map()

    source_url = event_payload.get("source_url") or ""
    if require_source and not source_url:
        return False

    score = float(event_payload.get("confidence_score") or 0.0)
    if score < min_conf:
        return False

    event_type = event_payload.get("event_type")
    if event_type not in {"confirmed_protest", "probable_protest", "related_unrest", "unresolved_location"}:
        return False

    has_coords = (
        event_payload.get("latitude") is not None and event_payload.get("longitude") is not None
    )
    if not has_coords and not allow_unresolved:
        return False

    return True


def build_event_payload(item):
    clean_text = str(item.get("clean_text") or "").strip()
    keyword_hits = detect_keywords(clean_text)
    place_result = resolve_place(clean_text)
    confidence_score, event_type = classify_event(clean_text, keyword_hits, place_result)

    source_url = canonicalize_source_url(item.get("link"))
    published_at = item.get("published_at_utc")
    if not isinstance(published_at, datetime):
        published_at = utcnow_naive()
    published_day = published_at.date()

    source_feed = item.get("source_feed") or ""
    source_name = display_source_name(
        source_feed=source_feed,
        source_url=source_url,
        fallback_name=extract_source_name(source_feed),
    )
    source_platform = extract_source_platform(source_url)
    dedupe_hash = build_dedupe_hash(clean_text, source_url, published_at, place_result)

    payload = {
        "source_feed": source_feed,
        "source_name": source_name,
        "source_guid": (item.get("guid") or "").strip(),
        "source_url": source_url,
        "source_platform": source_platform,
        "source_author": None,
        "source_published_at_utc": published_at,
        "published_day_utc": published_day,
        "raw_title": item.get("title") or "",
        "raw_description": item.get("raw_description") or "",
        "clean_text": clean_text,
        "detected_keywords_json": json.dumps(keyword_hits, ensure_ascii=False),
        "matched_place_text": place_result.get("matched_place_text"),
        "matched_feature_type": place_result.get("feature_type"),
        "matched_feature_name": place_result.get("feature_name"),
        "matched_province": place_result.get("province"),
        "matched_municipality": place_result.get("municipality"),
        "matched_locality": place_result.get("locality"),
        "latitude": place_result.get("latitude"),
        "longitude": place_result.get("longitude"),
        "location_precision": place_result.get("location_precision"),
        "confidence_score": confidence_score,
        "event_type": event_type,
        "review_status": "auto",
        "dedupe_hash": dedupe_hash,
        "transparency_note": "Fuente enlazada al post original.",
    }
    payload["visible_on_map"] = should_show_on_map(payload)
    return payload


def filter_recent_items(items, max_age_days):
    now = utcnow_naive()
    oldest = now - timedelta(days=max(1, int(max_age_days)))
    kept = []
    for item in items:
        published = item.get("published_at_utc")
        if not isinstance(published, datetime):
            kept.append(item)
            continue
        if published >= oldest:
            kept.append(item)
    return kept


def parse_feed_payload(xml_text, source_feed):
    items = parse_rss_items(xml_text, source_feed)
    items = filter_recent_items(items, get_max_post_age_days())
    limit = get_max_items_per_feed()
    if len(items) > limit:
        items = items[:limit]
    return items
