"""
Django settings for scanQR project.

Generated by 'django-admin startproject' using Django 5.1.5.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

from pathlib import Path
from datetime import timedelta
from celery.schedules import crontab
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from a .env file
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://13.61.11.100/")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-%fd*8k+6$lc5g*r2pnn(-9%ns-jsk&bmn_(@$*#nk_$7*btshl'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False
ALLOWED_HOSTS = ['*'] 

# ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'corsheaders',  # Add this
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_celery_results',
    'django_celery_beat',
    'auth_service',
    'qr_service',
    'call_service',
    'common',
    "channels",
]

ASGI_APPLICATION = "scanQR.asgi.application"

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Add this at the top
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "auth_service.middleware.BlockBlacklistedTokensMiddleware",
]

ROOT_URLCONF = 'scanQR.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'email_templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'debug': True,
        },
    },
]

WSGI_APPLICATION = 'scanQR.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'parking',
        'USER': 'riyaansh',
        'PASSWORD': 'Riyaan$hM07',
        'HOST': 'parking-db.chas2ao8emec.eu-north-1.rds.amazonaws.com',
        'PORT': '5432',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

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

AUTH_USER_MODEL = 'auth_service.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ]
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),  # Short-lived access token for security
    'REFRESH_TOKEN_LIFETIME': timedelta(days=60),  # Long-lived refresh token for persistent login
    'ROTATE_REFRESH_TOKENS': True,  # Issue a new refresh token when the current one is used
    'BLACKLIST_AFTER_ROTATION': True,  # Blacklist old refresh tokens after rotation
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',  # Ensure it aligns with your User model
    'USER_ID_CLAIM': 'user_id',
}

CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Redis message broker
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

# Store Celery task results
CELERY_RESULT_BACKEND = 'django-db'

# Celery Beat Config (For scheduled tasks)
CELERY_BEAT_SCHEDULE = {
    'clear_expired_otps_every_1_min': {
        'task': 'auth_service.tasks.clear_expired_otps',
        'schedule': crontab(minute='*/1'),  # Every 1 minutes
    },
    'cleanup_blacklisted_tokens_daily': {
        'task': 'auth_service.tasks.cleanup_blacklisted_tokens',
        'schedule': crontab(hour=0, minute=0),  # Runs every day at midnight
    },
}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "riyaanshmittal14@gmail.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = True  # Allow all origins (for development)

# OR specify allowed origins (for production)
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:3000",
#     "http://192.168.29.244:8000",  # Your React Native app running on the local network
# ]

CORS_ALLOW_CREDENTIALS = True
# CORS_ALLOW_HEADERS = [
#     "content-type",
#     "authorization",
#     "X-CSRFTOKEN",
#     "X-Requested-With",
# ]

