"""Django settings for the US Business Phone Number Collection Agent."""

from pathlib import Path
import sys

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

environ.Env.read_env(BASE_DIR / ".env")

# Required — never ship an insecure default (set in .env; see .env.example).
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
FRONTEND_ORIGINS = env.list(
    "FRONTEND_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([*CSRF_TRUSTED_ORIGINS, *FRONTEND_ORIGINS]))

if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
    )
    SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    # Only enable when TLS is terminated by a trusted reverse proxy.
    if env.bool("USE_PROXY_SSL_HEADER", default=False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "sources",
    "phones.apps.PhonesConfig",
    "acquisition.apps.AcquisitionConfig",
    "api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="phone_agent"),
        "USER": env("POSTGRES_USER", default="phone_agent"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="phone_agent_dev"),
        "HOST": env("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "OPTIONS": {
            "sslmode": env("POSTGRES_SSLMODE", default="prefer"),
        },
    }
}

if "test" in sys.argv:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# OpenStreetMap / Overpass (Phase 3)
OVERPASS_URL = env(
    "OVERPASS_URL",
    default="https://overpass-api.de/api/interpreter",
)
NOMINATIM_URL = env(
    "NOMINATIM_URL",
    default="https://nominatim.openstreetmap.org",
)
OVERPASS_USER_AGENT = env(
    "OVERPASS_USER_AGENT",
    default="PhoneCollectionAgent/0.1 (local-dev; contact=admin@localhost)",
)

# Celery / Redis (Phase 6 enrichment)
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 120
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "enrich-pending-hourly": {
        "task": "phones.tasks.enrich_pending_batch",
        "schedule": 3600.0,
        "kwargs": {"limit": 25},
    },
    "acquisition-cycle-30m": {
        "task": "acquisition.tasks.run_acquisition_cycle",
        "schedule": 1800.0,
    },
}
# Stale enrichment window (days) for beat / enrich_phones backfill
ENRICHMENT_STALE_DAYS = env.int("ENRICHMENT_STALE_DAYS", default=30)

# Phase 7 orchestration targets (comma-separated in .env)
ORCHESTRATION_CITIES = [
    c.strip()
    for c in env("ORCHESTRATION_CITIES", default="Austin,Dallas,Houston,San Antonio").split(",")
    if c.strip()
]
ORCHESTRATION_CATEGORIES = [
    c.strip().lower()
    for c in env("ORCHESTRATION_CATEGORIES", default="restaurant,cafe").split(",")
    if c.strip()
]
ORCHESTRATION_LIMIT = env.int("ORCHESTRATION_LIMIT", default=25)
SCRAPER_LOOP_SLEEP_SECONDS = env.int("SCRAPER_LOOP_SLEEP_SECONDS", default=10)

CORS_ALLOWED_ORIGINS = FRONTEND_ORIGINS
CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "api.permissions.IsStaffUser",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# Phase 9 hardening
HTTP_TIMEOUT = env.float("HTTP_TIMEOUT", default=30.0)
HTTP_MAX_RETRIES = env.int("HTTP_MAX_RETRIES", default=3)
SOURCE_ERROR_COOLDOWN_MINUTES = env.int("SOURCE_ERROR_COOLDOWN_MINUTES", default=60)
AUTHORIZED_CRAWL_DELAY_SECONDS = env.float("AUTHORIZED_CRAWL_DELAY_SECONDS", default=1.5)
AUTHORIZED_CRAWL_USER_AGENT = env(
    "AUTHORIZED_CRAWL_USER_AGENT",
    default="PhoneCollectionAgent/0.1 (authorized-crawl; contact=admin@localhost)",
)

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "sources": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "phones": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "acquisition": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        # httpx logs full request URLs at INFO (includes apiKey/key query params).
        "httpx": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "httpcore": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
