import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env for local development only
# --------------------------
if os.environ.get("RUNNING_LOCALLY", "True") == "True":
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")


# Security
# --------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-secret-key")
DEBUG = "True"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")

# Backup / Media    
# --------------------------
LOCAL_MIRROR_BASE = os.getenv("LOCAL_MIRROR_BASE", "/home/site/wwwroot/backups")
os.makedirs(LOCAL_MIRROR_BASE, exist_ok=True)
MEDIA_URL = "/backups/"
MEDIA_ROOT = LOCAL_MIRROR_BASE

# Installed apps
# --------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "purpleBackupApp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backupProject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "backupProject.wsgi.application"

# Database (MySQL)
# --------------------------
DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get(
            "DATABASE_URL",
            f"mysql://{os.environ.get('DB_USER')}:{os.environ.get('DB_PASSWORD')}@"
            f"{os.environ.get('DB_HOST','127.0.0.1')}:{os.environ.get('DB_PORT',3306)}/"
            f"{os.environ.get('DB_NAME')}"
        )
    )
}

# Patch MySQL "Specified key was too long" error if needed
from django.db.backends.mysql.base import DatabaseWrapper

orig_data_types = DatabaseWrapper.data_types

def patched_data_types(self):
    types = orig_data_types.__get__(self).copy()
    types["CharField"] = "varchar(191)"
    return types

DatabaseWrapper.data_types = property(patched_data_types)

# --------------------------
# Password validation
# --------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
# --------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# Static files
# --------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

STATIC_ROOT = BASE_DIR / "static_cdn" 
# Wasabi / backups
# --------------------------
WASABI_ACCESS_KEY = os.environ.get("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.environ.get("WASABI_SECRET_KEY")
WASABI_BUCKET = os.environ.get("WASABI_BUCKET")
WASABI_PREFIX = os.environ.get("WASABI_PREFIX", "")

# Celery
# --------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 60  # 1 hour max per task
CELERY_WORKER_POOL = "solo"  # Windows compatible
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Karachi"


# Production security for Azure
# --------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Default primary key
# --------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
