# rag_project/settings.py

from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
DEBUG      = os.getenv("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1"
).split(",")

# ── Apps ──────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_ratelimit",
    "rag_app",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rag_project.urls"

TEMPLATES = [{
    "BACKEND":  "django.template.backends.django.DjangoTemplates",
    "DIRS":     [],
    "APP_DIRS": True,
    "OPTIONS":  {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

WSGI_APPLICATION = "rag_project.wsgi.application"

# ── Database — Neon in production, local PostgreSQL in dev ────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE":   "django.db.backends.postgresql",
            "NAME":     os.getenv("DB_NAME",     "ragdb"),
            "USER":     os.getenv("DB_USER",     "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", "yourpassword"),
            "HOST":     os.getenv("DB_HOST",     "localhost"),
            "PORT":     os.getenv("DB_PORT",     "5432"),
        }
    }

# ── Cache / Redis — Upstash in production ─────────────────────────────────────
REDIS_URL  = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USE_REDIS  = os.getenv("USE_REDIS", "true").lower() == "true"

if USE_REDIS:
    CACHES = {
        "default": {
            "BACKEND":  "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept", "authorization", "content-type", "x-csrftoken",
]

# ── DRF + JWT ──────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 60))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", 7))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES":     ("Bearer",),
}

# ── Static files — WhiteNoise serves from Render ──────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── ChromaDB path — writeable inside Render container ─────────────────────────
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_store")

# ── Misc ───────────────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD   = "django.db.models.BigAutoField"
SESSION_TTL_SECONDS  = int(os.getenv("SESSION_TTL_SECONDS", 86400))
MAX_HISTORY_TURNS    = int(os.getenv("MAX_HISTORY_TURNS", 10))

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_I18N      = True
USE_TZ        = True