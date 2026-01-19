import os
import sys
import json
from flask import Flask, render_template, redirect, url_for
from flask_cors import CORS

from . import config
from .utils.logging import setup_logging

# ---------------------------------------------------------------------------
# Vendor path configuration (openpyxl fallback)
vendor_dir = os.path.join(config.ROOT_DIR, "vendor")
if os.path.isdir(vendor_dir) and vendor_dir not in sys.path:
    sys.path.append(vendor_dir)

def create_app():
    from .extensions import login_manager
    from .db import init_db, ensure_migrations

    logger = setup_logging()
    app = Flask(
        __name__,
        template_folder=os.path.join(config.ROOT_DIR, "templates"),
        static_folder=os.path.join(config.ROOT_DIR, "static"),
    )
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = False

    if config.TRUST_PROXY_HEADERS:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=config.PROXY_FIX_X_FOR)

    CORS(app, supports_credentials=True)
    login_manager.init_app(app)
    login_manager.login_view = "index"

    # Lazily initialize DB/files on first request to match original behavior.
    _db_initialized = {"done": False}

    @app.before_request
    def first_request_setup():
        if _db_initialized["done"]:
            return
        init_db()
        ensure_migrations()
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

        archive_path = config.ARCHIVE_PATH
        try:
            if not os.path.exists(archive_path):
                from openpyxl import Workbook
                wb = Workbook()
                ws = wb.active
                ws.append(
                    [
                        "id",
                        "object_name",
                        "address",
                        "lat",
                        "lon",
                        "description",
                        "priority",
                        "email",
                        "status",
                        "close_reason",
                        "assigned_master_id",
                        "assigned_master_name",
                        "created_at",
                        "updated_at",
                        "arrived_at",
                        "completed_at",
                        "archived_at",
                    ]
                )
                wb.save(archive_path)
        except Exception as e:
            print("Failed to initialize archive file:", e)

        _db_initialized["done"] = True

    @app.get("/")
    def index():
        from .tickets.service import CancelReason
        from flask_login import current_user
        from .utils.roles import is_technician

        if current_user.is_authenticated and is_technician(current_user.role):
            return redirect("/mobile")

        return render_template(
            "index.html",
            cancel_reasons=[reason.value for reason in CancelReason],
        )

    @app.get("/mobile")
    def mobile():
        from flask_login import current_user
        from .utils.roles import is_technician

        if not current_user.is_authenticated:
            return render_template("mobile_login.html", next_url="/mobile")
        if not is_technician(current_user.role):
            return render_template("mobile_not_technician.html")
        return render_template("mobile.html", username=current_user.username)

    from .auth.routes import bp as auth_bp
    from .access.routes import bp as access_bp
    from .tickets.routes import bp as tickets_bp
    from .assets.routes import bp as assets_bp
    from .objects.routes import bp as objects_bp
    from .utils.health import bp as health_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(access_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(objects_bp)
    app.register_blueprint(health_bp)

    from werkzeug.exceptions import HTTPException
    from flask import request, jsonify

    def _json_error(code: int, message: str):
        return jsonify({"error": {"code": code, "message": message}})

    @login_manager.unauthorized_handler
    def handle_unauthorized():
        if request.path.startswith("/api"):
            logger.warning(
                "Unauthorized access",
                extra={"status_code": 401, "path": request.path, "method": request.method},
            )
            return _json_error(401, "Unauthorized"), 401
        target = login_manager.login_view or "index"
        return redirect(url_for(target, next=request.url))

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        # Preserve HTML responses for non-API routes
        if not request.path.startswith("/api"):
            return err
        logger.warning("HTTP error", extra={"status_code": err.code, "path": request.path, "method": request.method})
        return _json_error(err.code, err.description), err.code

    @app.errorhandler(Exception)
    def handle_generic_error(err):
        if not request.path.startswith("/api"):
            raise err
        logger.exception("Unhandled error", extra={"path": request.path, "method": request.method})
        return _json_error(500, "Internal Server Error"), 500

    @app.after_request
    def normalize_api_errors(response):
        # Only normalize API error responses (non-2xx/3xx)
        if not request.path.startswith("/api") or response.status_code < 400:
            return response
        data = None
        try:
            data = response.get_json(silent=True)
        except Exception:
            return response
        if not isinstance(data, dict):
            return response
        # If already in the new format, keep it
        if isinstance(data.get("error"), dict) and "code" in data["error"] and "message" in data["error"]:
            return response
        message = data.get("error") if isinstance(data.get("error"), (str, int, float)) else response.status
        wrapped = {"error": {"code": response.status_code, "message": str(message)}}
        response.set_data(json.dumps(wrapped))
        response.mimetype = "application/json"
        return response

    return app
