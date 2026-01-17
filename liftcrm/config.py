import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARCHIVE_PATH = os.path.join(ROOT_DIR, "archive.xlsx")
OBJECTS_DIR = os.path.join(ROOT_DIR, "objects")
UPLOAD_FOLDER = os.path.join(ROOT_DIR, "uploads")
DB_PATH = os.path.join(ROOT_DIR, "lift_crm.db")

# Security / auth
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
DISPATCHER_USERNAME = os.environ.get("DISPATCHER_USERNAME", "dispatcher")
DISPATCHER_PASSWORD = os.environ.get("DISPATCHER_PASSWORD", "disp123")
TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")
PROXY_FIX_X_FOR = int(os.environ.get("PROXY_FIX_X_FOR", 1))

# SLA
SLA_RESPONSE_MINUTES = int(os.environ.get("SLA_RESPONSE_MINUTES", 30))
SLA_COMPLETION_MINUTES = int(os.environ.get("SLA_COMPLETION_MINUTES", 120))

# SMTP (optional)
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
