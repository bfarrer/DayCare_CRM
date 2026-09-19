"""Application configuration.

The only setting that changes between the local prototype and a shared
team database is DATABASE_URL, so the move to Postgres stays a config edit.
"""

import os
import secrets


class Config:
    # A missing SECRET_KEY would silently invalidate every session on restart,
    # so generate one per-process and warn at startup instead (see create_app).
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///daycare_crm.sqlite3")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Sessions expire so an unattended front-desk machine does not stay signed in.
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME_SECONDS", 60 * 60 * 12))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Only enforce HTTPS-only cookies once the app is actually served over TLS.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

    WTF_CSRF_TIME_LIMIT = None

    DAYCARE_NAME = os.environ.get("DAYCARE_NAME", "Red Fern Child Care")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
