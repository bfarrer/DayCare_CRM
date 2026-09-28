"""Application configuration.

Local development runs on SQLite and creates its own tables. Production runs
on PostgreSQL and uses Alembic migrations. The only required difference is
DATABASE_URL; everything else has a safe default.
"""

import os
import secrets


def _normalize_database_url(url):
    """Accept the postgres:// URLs that hosting providers hand out.

    Render and others still emit 'postgres://', which SQLAlchemy 2.x does not
    recognize, and we pin the psycopg (v3) driver explicitly so the URL does
    not fall back to psycopg2, which is not installed.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _is_postgres(url):
    return bool(url) and url.startswith("postgresql")


class Config:
    # A missing SECRET_KEY would silently invalidate every session on restart,
    # so generate one per-process and warn at startup instead (see create_app).
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    SQLALCHEMY_DATABASE_URI = _normalize_database_url(
        os.environ.get("DATABASE_URL", "sqlite:///daycare_crm.sqlite3")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Recycle connections well inside the idle timeouts that managed Postgres
    # providers apply, so a connection is never handed to a request after the
    # server has already dropped it.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", 280)),
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 5)),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 2)),
    }

    # SQLite has no server to migrate against, so the local prototype still
    # creates its tables on first run. Postgres deployments use Alembic.
    AUTO_CREATE_TABLES = not _is_postgres(SQLALCHEMY_DATABASE_URI)

    # Sessions expire so an unattended front-desk machine does not stay signed in.
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME_SECONDS", 60 * 60 * 12))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Served over HTTPS in production, so the cookie must not travel in clear.
    # Defaults on whenever a hosting provider is detected, and stays off for
    # local http://127.0.0.1 development.
    SESSION_COOKIE_SECURE = os.environ.get(
        "SESSION_COOKIE_SECURE", "1" if os.environ.get("RENDER") else "0"
    ) == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_TIME_LIMIT = None

    # Behind a reverse proxy, trust the forwarded scheme/host headers so
    # url_for builds https:// links and the secure cookie is actually set.
    BEHIND_PROXY = os.environ.get("BEHIND_PROXY", "1" if os.environ.get("RENDER") else "0") == "1"

    # Set DAYCARE_NAME in .env (local) or the host's environment variables
    # (production) to the real name. It is deliberately not committed, so the
    # daycare's name never appears in the repository.
    DAYCARE_NAME = os.environ.get("DAYCARE_NAME", "Daycare CRM")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AUTO_CREATE_TABLES = False
    SESSION_COOKIE_SECURE = False
    BEHIND_PROXY = False
    WTF_CSRF_ENABLED = False
