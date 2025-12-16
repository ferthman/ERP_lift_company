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
MASTER_PASSWORD = os.environ.get("MASTER_PASSWORD", "m123456")

# SMTP (optional)
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
