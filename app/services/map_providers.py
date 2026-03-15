from app.services.settings import get_setting, set_setting


MAP_PROVIDER_LEAFLET = "leaflet"
MAP_PROVIDER_GOOGLE = "google"
ALLOWED_MAP_PROVIDERS = {MAP_PROVIDER_LEAFLET, MAP_PROVIDER_GOOGLE}


def normalize_map_provider(value, default=MAP_PROVIDER_LEAFLET):
    provider = (value or "").strip().lower()
    if provider in ALLOWED_MAP_PROVIDERS:
        return provider
    return default


def get_map_provider_main():
    return normalize_map_provider(
        get_setting("map_provider_main", MAP_PROVIDER_LEAFLET),
        MAP_PROVIDER_LEAFLET,
    )


def get_map_provider_forms():
    return normalize_map_provider(
        get_setting("map_provider_forms", MAP_PROVIDER_LEAFLET),
        MAP_PROVIDER_LEAFLET,
    )


def set_map_provider_main(value):
    provider = normalize_map_provider(value, MAP_PROVIDER_LEAFLET)
    set_setting("map_provider_main", provider)
    return provider


def set_map_provider_forms(value):
    provider = normalize_map_provider(value, MAP_PROVIDER_LEAFLET)
    set_setting("map_provider_forms", provider)
    return provider
