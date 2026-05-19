from pathlib import Path
import os
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]



# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'CoffeeQual IA.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'CoffeeQual IA.wsgi.application'


# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 120,
        "OPTIONS": {
            "options": f"-c search_path={os.getenv('DB_SCHEMA', 'public')},public"
        },
    }
}



# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'es-mx'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@coffeequal.local"


# Cameras
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _build_camera_sources():
    cameras = {}

    # =========================
    # CAM1
    # =========================
    cam1_sources = []

    cam1_type = os.getenv("CAM1_TYPE", "").strip().lower()
    cam1_index = _env_int("CAM1_INDEX", 0)
    cam1_rtsp = os.getenv("CAM1_RTSP_URL", "").strip()

    cam1_fallback_type = os.getenv("CAM1_FALLBACK_TYPE", "").strip().lower()
    cam1_fallback_url = os.getenv("CAM1_FALLBACK_URL", "").strip()
    cam1_fallback_index = _env_int("CAM1_FALLBACK_INDEX", 1)

    # Principal CAM1
    if cam1_type == "rtsp" and cam1_rtsp:
        cam1_sources.append({
            "name": "cam1_main",
            "type": "rtsp",
            "url": cam1_rtsp,
        })
    elif cam1_type == "device":
        cam1_sources.append({
            "name": "cam1_main",
            "type": "device",
            "index": cam1_index,
        })

    # Fallback CAM1
    if cam1_fallback_type == "rtsp" and cam1_fallback_url:
        cam1_sources.append({
            "name": "cam1_fallback",
            "type": "rtsp",
            "url": cam1_fallback_url,
        })
    elif cam1_fallback_type == "device":
        cam1_sources.append({
            "name": "cam1_fallback",
            "type": "device",
            "index": cam1_fallback_index,
        })

    if cam1_sources:
        cameras["cam1"] = cam1_sources

    # =========================
    # CAM2
    # =========================.
    cam2_sources = []

    cam2_type = os.getenv("CAM2_TYPE", "").strip().lower()
    cam2_index = _env_int("CAM2_INDEX", 2)
    cam2_rtsp = os.getenv("CAM2_RTSP_URL", "").strip()

    if cam2_type == "rtsp" and cam2_rtsp:
        cam2_sources.append({
            "name": "cam2_main",
            "type": "rtsp",
            "url": cam2_rtsp,
        })
    elif cam2_type == "device":
        cam2_sources.append({
            "name": "cam2_main",
            "type": "device",
            "index": cam2_index,
        })

    if cam2_sources:
        cameras["cam2"] = cam2_sources

    return cameras


CAMERA_SOURCES = _build_camera_sources()

# Motor ESP32 / Banda transportadora
MOTOR_SERIAL_PORT = os.getenv("MOTOR_SERIAL_PORT", "AUTO")
MOTOR_SERIAL_BAUDRATE = int(os.getenv("MOTOR_SERIAL_BAUDRATE", "115200"))
MOTOR_SERIAL_TIMEOUT = float(os.getenv("MOTOR_SERIAL_TIMEOUT", "1"))
MOTOR_SERIAL_ID = os.getenv("MOTOR_SERIAL_ID", "COFFEEVISION_MOTOR_ESP32")

# http://127.0.0.1:8000/
