class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SERVER_NAME = "localhost"
    CLOUDINARY_CLOUD_NAME = ""
    RECAPTCHA_V2_SITE_KEY = ""
    VAPID_PUBLIC_KEY = ""
