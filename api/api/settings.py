import json
import os
from pathlib import Path

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dummykey")
DEBUG = int(os.getenv("DEBUG_VALUE", 1))
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"


ALLOWED_HOSTS = os.getenv(
    "DJANGO_ALLOWED_HOSTS", "api.localhost,auth.localhost,localhost"
).split(",")
ROOT_URLCONF = "api.urls"
ROOT_HOSTCONF = "api.hosts"
DEFAULT_HOST = "api"
WSGI_APPLICATION = "api.wsgi.application"


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.sites",
    "rest_framework",
    "rest_framework.authtoken",
    "django_q",
    "django_filters",
    "django_extensions",
    "django_hosts",
    "django_admin_shell",
    "beers",
    "corsheaders",
]

MIDDLEWARE = [
    "django_hosts.middleware.HostsRequestMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_hosts.middleware.HostsResponseMiddleware",
]


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.{}".format(
            os.getenv("DATABASE_ENGINE", "postgresql")
        ),
        "NAME": os.getenv("DATABASE_NAME", "beerdb"),
        "USER": os.getenv("DATABASE_USERNAME", "beer"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD", "123123"),
        "HOST": os.getenv("DATABASE_HOST", "127.0.0.1"),
        "PORT": os.getenv("DATABASE_PORT", 5432),
        "OPTIONS": json.loads(os.getenv("DATABASE_OPTIONS", "{}")),
    }
}


SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
]


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "accounts/templates/account",
        ],
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


STATIC_ROOT = "/static2"
STATIC_URL = "/static2/"


LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True


CORS_ALLOWED_ORIGINS = [
    "https://www.vinmonopolet.no",
    "https://app.vinmonopolet.no",
    "https://olmonopolet.app",
    "https://www.olmonopolet.app",
    "http://localhost:5173",
]
CORS_ALLOW_METHODS = [
    "GET",
]
CSRF_TRUSTED_ORIGINS = [
    "https://api.beermonopoly.com",
    "https://api.olmonopolet.app",
    "https://auth.beermonopoly.com",
]


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
}


Q_CLUSTER = {
    "name": "beerapi",
    "orm": "default",
    "timeout": 3600,
    "retry": 4000,
    "save_limit": 50,
    "save_limit_per": "func",
    "ack_failures": True,
    "catch_up": False,
    "recycle": 10,
    "cpu_affinity": 1,
    "max_attempts": 1,
    "attempt_count": 1,
    "label": "Django Q",
    "error_reporter": {
        "sentry": {
            "dsn": "https://6d8c8869d8c64767b26de850f794bc4c@o985007.ingest.sentry.io/5941029"
        }
    },
}


NOTEBOOK_ARGUMENTS = [
    "--ip",
    "0.0.0.0",
    "--port",
    "8888",
    "--allow-root",
    "--no-browser",
]
IPYTHON_ARGUMENTS = [
    "--ext",
    "django_extensions.management.notebook_extension",
]


if not DEBUG:
    sentry_sdk.init(
        dsn="https://6d8c8869d8c64767b26de850f794bc4c@o985007.ingest.sentry.io/5941029",
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.2,
        send_default_pii=True,
    )
