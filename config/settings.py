import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/soscubamap",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = True
    APP_NAME = "#SOSCuba Map"
    DEFAULT_LANGUAGE = "es"
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
    GOOGLE_MAPS_MAP_ID = os.getenv("GOOGLE_MAPS_MAP_ID", "")
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
    IMAGE_MAX_MB = int(os.getenv("IMAGE_MAX_MB", "2"))
    IMAGE_MAX_PER_SUBMIT = int(os.getenv("IMAGE_MAX_PER_SUBMIT", "3"))
    IMAGE_ALLOWED_EXTENSIONS = os.getenv(
        "IMAGE_ALLOWED_EXTENSIONS",
        "jpg,jpeg,png,webp,heic",
    )
    GEOJSON_PROVINCES_PATH = os.getenv("GEOJSON_PROVINCES_PATH", "")
    GEOJSON_MUNICIPALITIES_PATH = os.getenv("GEOJSON_MUNICIPALITIES_PATH", "")
    GEOJSON_PROVINCE_KEYS = os.getenv("GEOJSON_PROVINCE_KEYS", "")
    GEOJSON_MUNICIPALITY_KEYS = os.getenv("GEOJSON_MUNICIPALITY_KEYS", "")
    GEOJSON_MUNICIPALITY_PROVINCE_KEYS = os.getenv("GEOJSON_MUNICIPALITY_PROVINCE_KEYS", "")
    POSTS_REQUIRE_MODERATION = True
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@soscuba.local")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    RATELIMIT_STORAGE_URL = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "1") == "1"
    RECAPTCHA_V2_SITE_KEY = os.getenv("RECAPTCHA_V2_SITE_KEY", "")
    RECAPTCHA_V2_SECRET_KEY = os.getenv("RECAPTCHA_V2_SECRET_KEY", "")
    CHAT_DISABLED = os.getenv("CHAT_DISABLED", "0") == "1"
    ASSET_VERSION = os.getenv("ASSET_VERSION", "1")
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:soscubamap@proton.me")
    CLOUDFLARE_RADAR_HTTP_TIMESERIES_URL = os.getenv(
        "CLOUDFLARE_RADAR_HTTP_TIMESERIES_URL",
        "https://api.cloudflare.com/client/v4/radar/http/timeseries?name=main&name=previous&geoId=3556965&geoId=3556965&dateRange=1d&dateRange=1dControl",
    )
    CONNECTIVITY_FETCH_DELAY_SECONDS = int(os.getenv("CONNECTIVITY_FETCH_DELAY_SECONDS", "120"))
    CONNECTIVITY_FETCH_TIMEOUT_SECONDS = int(os.getenv("CONNECTIVITY_FETCH_TIMEOUT_SECONDS", "30"))
    CONNECTIVITY_STALE_AFTER_HOURS = int(os.getenv("CONNECTIVITY_STALE_AFTER_HOURS", "8"))
    CONNECTIVITY_FRONTEND_REFRESH_SECONDS = int(
        os.getenv("CONNECTIVITY_FRONTEND_REFRESH_SECONDS", "300")
    )
