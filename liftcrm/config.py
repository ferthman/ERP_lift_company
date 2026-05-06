import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARCHIVE_PATH = os.path.join(ROOT_DIR, "archive.xlsx")
OBJECTS_DIR = os.path.join(ROOT_DIR, "objects")
UPLOAD_FOLDER = os.path.join(ROOT_DIR, "uploads")
DB_PATH = os.path.join(ROOT_DIR, "lift_crm.db")

# Security / auth
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
APP_ENV = os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development"
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
DISPATCHER_USERNAME = os.environ.get("DISPATCHER_USERNAME", "dispatcher")
DISPATCHER_PASSWORD = os.environ.get("DISPATCHER_PASSWORD", "disp123")
TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")
PROXY_FIX_X_FOR = int(os.environ.get("PROXY_FIX_X_FOR", 1))

_WEAK_SECRET_KEYS = {
    "",
    "dev-secret",
    "change-me",
    "changeme",
    "secret",
    "password",
    "insecure",
}


def get_app_env():
    return (os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or APP_ENV or "development").strip().lower()


def is_production():
    return get_app_env() == "production"


def _parse_bool_env(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv_env(name):
    raw = os.environ.get(name, "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def get_secret_key():
    return os.environ.get("SECRET_KEY", SECRET_KEY)


def validate_secret_key():
    secret = get_secret_key()
    if not is_production():
        return secret
    if "SECRET_KEY" not in os.environ:
        raise RuntimeError("SECRET_KEY must be set in production")
    if not isinstance(secret, str) or secret.strip().lower() in _WEAK_SECRET_KEYS or len(secret.strip()) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters and non-default in production")
    return secret


def session_cookie_config():
    production = is_production()
    same_site = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax").strip() or "Lax"
    return {
        "SESSION_COOKIE_HTTPONLY": _parse_bool_env("SESSION_COOKIE_HTTPONLY", True),
        "SESSION_COOKIE_SAMESITE": same_site,
        "SESSION_COOKIE_SECURE": _parse_bool_env("SESSION_COOKIE_SECURE", production),
    }


def cors_allowed_origins():
    origins = _parse_csv_env("CORS_ALLOWED_ORIGINS")
    if any(origin == "*" for origin in origins):
        raise RuntimeError("CORS_ALLOWED_ORIGINS cannot include '*' when credentials are supported")
    return origins

# SLA
SLA_RESPONSE_MINUTES = int(os.environ.get("SLA_RESPONSE_MINUTES", 30))
SLA_COMPLETION_MINUTES = int(os.environ.get("SLA_COMPLETION_MINUTES", 120))

# SMTP (optional)
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
