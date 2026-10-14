"""Django settings for the Weather-Aware Truck Routing API.

Every integration is key-free by default (Valhalla + Open-Meteo + Nominatim), so a
fresh clone can plan a trip without any account sign-up.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [part.strip() for part in os.environ.get(name, default).split(",") if part.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-weather-truck-routing")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")


def _add_host(host: str) -> None:
    host = host.removeprefix("https://").removeprefix("http://").split("/")[0].strip()
    if host and host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)


def _add_origin(origin: str) -> None:
    origin = origin.strip().rstrip("/")
    if not origin:
        return
    if not origin.startswith(("http://", "https://")):
        origin = f"https://{origin}"
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)


# Render injects this for every web service.
if env("RENDER_EXTERNAL_HOSTNAME"):
    _add_host(env("RENDER_EXTERNAL_HOSTNAME"))
    _add_origin(env("RENDER_EXTERNAL_HOSTNAME"))

# Vercel Python / serverless: rotating preview hosts + production alias.
for key in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    if env(key):
        _add_host(env(key))
        _add_origin(env(key))

ON_VERCEL = env_bool("VERCEL", False) or bool(env("VERCEL_URL"))
if ON_VERCEL:
    # Matches weather-aware-truck-routing-green.vercel.app and other previews.
    _add_host(".vercel.app")
    _add_origin("https://*.vercel.app")

# Vercel’s deployment FS is read-only; only /tmp is writable (ephemeral).
DATA_DIR = Path("/tmp/wayline") if ON_VERCEL else BASE_DIR
if ON_VERCEL:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
if env_bool("DJANGO_BEHIND_PROXY", False) or ON_VERCEL:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "routing",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

_default_sqlite = DATA_DIR / "db.sqlite3"
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", f"sqlite:///{_default_sqlite}"),
        # Serverless: avoid sticky connections across cold starts.
        conn_max_age=0 if ON_VERCEL else 600,
    )
}
if ON_VERCEL and not env("DATABASE_URL"):
    # Cache sessions so middleware does not require a warm SQLite file.
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "UNAUTHENTICATED_USER": None,
}

CORS_ALLOWED_ORIGINS: list[str] = []


def _add_cors_origin(origin: str) -> None:
    origin = origin.strip().rstrip("/")
    if not origin:
        return
    if not origin.startswith(("http://", "https://")):
        origin = f"https://{origin}"
    if origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(origin)


# UI origin(s). Override with CORS_ALLOWED_ORIGINS in the host env (comma-separated).
for origin in env_list(
    "CORS_ALLOWED_ORIGINS",
    "https://weather-aware-truck-routing-tulv.vercel.app",
):
    _add_cors_origin(origin)

# Any *.vercel.app UI (preview + production aliases).
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://[a-zA-Z0-9.-]+\.vercel\.app$"]

# Local debug, explicit flag, or Vercel API host: allow browser UIs to call the API.
CORS_ALLOW_ALL_ORIGINS = (
    DEBUG or env_bool("CORS_ALLOW_ALL", False) or ON_VERCEL
)


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "weather-truck-routing",
        "TIMEOUT": env_int("CACHE_TIMEOUT", 1800),
        "OPTIONS": {"MAX_ENTRIES": 10000},
    }
}

# ---------------------------------------------------------------------------
# Upstream providers (all key-free).
# ---------------------------------------------------------------------------
ROUTING_PROVIDER = env("ROUTING_PROVIDER", "valhalla").strip().lower()
VALHALLA_BASE_URL = env("VALHALLA_BASE_URL", "https://valhalla1.openstreetmap.de").rstrip("/")
ROUTING_CLIENT_ID = env("ROUTING_CLIENT_ID", "wayline-assessment-local")
OSRM_BASE_URL = env("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
NOMINATIM_URL = env("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")
PHOTON_URL = env("PHOTON_URL", "https://photon.komoot.io").rstrip("/")
OPEN_METEO_URL = env("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast").rstrip("/")
GEOCODER_USER_AGENT = env(
    "GEOCODER_USER_AGENT", "weather-truck-routing/1.0 (assessment demo)"
)
# A shared file coordinates all threads/workers on this host. The default
# public Nominatim provider must not be used by multiple application hosts.
GEOCODER_RATE_LIMIT_DB = env(
    "GEOCODER_RATE_LIMIT_DB", str(DATA_DIR / "geocoder-rate-limit.sqlite3")
)


WEATHER_CHUNK_SIZE = env_int("WEATHER_CHUNK_SIZE", 50)
WEATHER_MAX_WORKERS = env_int("WEATHER_MAX_WORKERS", 2)
UPSTREAM_TIMEOUT = max(1, env_int("UPSTREAM_TIMEOUT", 10))
ROUTING_TIMEOUT = max(1, env_int("ROUTING_TIMEOUT", 15))

HEATMAP_CORRIDOR_RADIUS_MILES = env_int("HEATMAP_CORRIDOR_RADIUS_MILES", 35)
HEATMAP_MAX_CELLS = env_int("HEATMAP_MAX_CELLS", 240)
