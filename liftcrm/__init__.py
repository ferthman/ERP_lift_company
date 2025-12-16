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

        os.makedirs(config.OBJECTS_DIR, exist_ok=True)
        xlsx_path = os.path.join(config.OBJECTS_DIR, "objects.xlsx")
        json_path = os.path.join(config.OBJECTS_DIR, "objects.json")
        sample_object = {
            "object_name": "Central Almaty",
            "address": "ул. Кабанбай Батыра 123",
            "lat": 43.238949,
            "lon": 76.889709,
        }
        try:
            if not os.path.exists(xlsx_path):
                try:
                    from openpyxl import Workbook
                    wb = Workbook()
                    ws = wb.active
                    ws.append(["object_name", "address", "lat", "lon"])
                    ws.append(
                        [
                            sample_object["object_name"],
                            sample_object["address"],
                            sample_object["lat"],
                            sample_object["lon"],
                        ]
                    )
                    wb.save(xlsx_path)
                except Exception as e:
                    print("Failed to create objects.xlsx:", e)
            if not os.path.exists(json_path):
                import json
                with open(json_path, "w", encoding="utf-8") as jf:
                    json.dump([sample_object], jf, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Failed to initialize objects files:", e)

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
                        "email",
                        "status",
                        "assigned_master_id",
                        "assigned_master_name",
                        "created_at",
                        "updated_at",
                        "arrived_at",
                        "completed_at",
                    ]
                )
                wb.save(archive_path)
        except Exception as e:
            print("Failed to initialize archive file:", e)

        _db_initialized["done"] = True

    @app.get("/")
    def index():
        return render_template("index.html")

    from .auth.routes import bp as auth_bp
    from .tickets.routes import bp as tickets_bp
    from .objects.routes import bp as objects_bp
    from .utils.health import bp as health_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tickets_bp)
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
