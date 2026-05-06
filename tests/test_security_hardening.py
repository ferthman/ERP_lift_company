import importlib
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from liftcrm import config, create_app
from liftcrm.utils.rate_limit import clear_rate_limits
from liftcrm.utils.roles import ROLE_TECHNICIAN


class SecurityHardeningTest(unittest.TestCase):
    def setUp(self):
        clear_rate_limits()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        self.original_archive_path = config.ARCHIVE_PATH
        self.original_upload_folder = config.UPLOAD_FOLDER
        config.DB_PATH = os.path.join(self.tmpdir.name, "security.db")
        config.ARCHIVE_PATH = os.path.join(self.tmpdir.name, "archive.xlsx")
        config.UPLOAD_FOLDER = os.path.join(self.tmpdir.name, "uploads")
        self._reload_db_bound_modules()

    def tearDown(self):
        config.DB_PATH = self.original_db_path
        config.ARCHIVE_PATH = self.original_archive_path
        config.UPLOAD_FOLDER = self.original_upload_folder
        self._reload_db_bound_modules()
        self.tmpdir.cleanup()

    def _reload_db_bound_modules(self):
        module_names = [
            "liftcrm.db",
            "liftcrm.tickets.repository",
            "liftcrm.tickets.service",
            "liftcrm.auth.routes",
            "liftcrm.access.routes",
            "liftcrm.assets.routes",
            "liftcrm.objects.routes",
            "liftcrm.tickets.routes",
        ]
        for name in module_names:
            module = importlib.import_module(name)
            importlib.reload(module)

    def _app(self):
        app = create_app()
        app.config["TESTING"] = True
        return app

    def _login_admin(self, client, origin=None):
        headers = {"Origin": origin} if origin else {}
        res = client.post(
            "/api/login",
            json={"username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD},
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        return res

    def _create_ticket(self, client, origin=None):
        headers = {"Origin": origin} if origin else {}
        res = client.post(
            "/api/tickets",
            json={
                "object_name": f"Security ticket {uuid.uuid4().hex[:8]}",
                "lat": 43.238949,
                "lon": 76.889709,
                "description": "Security hardening regression",
            },
            headers=headers,
        )
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def test_unsafe_cross_origin_state_change_is_rejected(self):
        app = self._app()
        client = app.test_client()
        self._login_admin(client)

        res = client.post(
            "/api/tickets",
            json={"object_name": "Blocked", "lat": 43.2, "lon": 76.9},
            headers={"Origin": "https://evil.example"},
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["error"]["message"], "Cross-origin state-changing request rejected")

    def test_valid_same_origin_state_change_is_accepted(self):
        app = self._app()
        client = app.test_client()
        same_origin = "http://localhost"
        self._login_admin(client, origin=same_origin)

        ticket_id = self._create_ticket(client, origin=same_origin)

        self.assertIsInstance(ticket_id, int)

    def test_login_still_works_without_browser_origin_header(self):
        app = self._app()
        client = app.test_client()

        res = self._login_admin(client)

        self.assertEqual(res.get_json()["ok"], True)

    def test_ticket_create_and_update_still_work_same_origin(self):
        app = self._app()
        client = app.test_client()
        same_origin = "http://localhost"
        self._login_admin(client, origin=same_origin)
        ticket_id = self._create_ticket(client, origin=same_origin)

        patch_res = client.patch(
            f"/api/tickets/{ticket_id}",
            json={"priority": "HIGH"},
            headers={"Origin": same_origin},
        )

        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["priority"], "HIGH")

    def test_mobile_sync_still_works_same_origin(self):
        app = self._app()
        client = app.test_client()
        same_origin = "http://localhost"
        tech_username = f"security_tech_{uuid.uuid4().hex[:8]}"
        tech_password = "security-tech-pass"
        self._db().init_db()
        with self._db_session() as db:
            master = self._db().Master(name="Security Sync Master", is_active=1)
            db.add(master)
            db.commit()
            db.refresh(master)
            user = self._db().User(
                username=tech_username,
                password_hash=generate_password_hash(tech_password),
                role=ROLE_TECHNICIAN,
                master_id=master.id,
                is_active=1,
            )
            ticket = self._db().Ticket(
                object_name="Security sync ticket",
                address="Test address",
                lat=43.238949,
                lon=76.889709,
                status="ASSIGNED",
                assigned_master_id=master.id,
                assigned_at=datetime.now(timezone.utc),
            )
            db.add_all([user, ticket])
            db.commit()
            ticket_id = ticket.id

        login_res = client.post(
            "/api/login",
            json={"username": tech_username, "password": tech_password},
            headers={"Origin": same_origin},
        )
        self.assertEqual(login_res.status_code, 200)

        res = client.post(
            "/api/sync/events",
            json={
                "events": [
                    {
                        "id": str(uuid.uuid4()),
                        "type": "TICKET_ACCEPT",
                        "ticket_id": ticket_id,
                        "expected_version": 1,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "payload": {},
                    }
                ]
            },
            headers={"Origin": same_origin},
        )

        self.assertEqual(res.status_code, 200)
        result = res.get_json()["results"][0]
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "OK")

    def _db(self):
        return importlib.import_module("liftcrm.db")

    def _db_session(self):
        return self._db().SessionLocal()

    def test_production_secret_key_is_required_and_must_be_strong(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY must be set"):
                create_app()

        with patch.dict(os.environ, {"APP_ENV": "production", "SECRET_KEY": "short"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY must be at least 32 characters"):
                create_app()

        strong_secret = "a" * 32
        with patch.dict(os.environ, {"APP_ENV": "production", "SECRET_KEY": strong_secret}, clear=True):
            app = create_app()
            self.assertEqual(app.config["SECRET_KEY"], strong_secret)

    def test_cookie_config_is_local_friendly_and_production_hardened(self):
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True):
            app = create_app()
            self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
            self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")
            self.assertFalse(app.config["SESSION_COOKIE_SECURE"])

        with patch.dict(os.environ, {"APP_ENV": "production", "SECRET_KEY": "b" * 32}, clear=True):
            app = create_app()
            self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
            self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")
            self.assertTrue(app.config["SESSION_COOKIE_SECURE"])

    def test_cors_does_not_allow_wildcard_credentialed_access(self):
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True):
            app = self._app()
            client = app.test_client()
            res = client.get("/api/me", headers={"Origin": "https://evil.example"})
            self.assertNotIn("Access-Control-Allow-Origin", res.headers)
            self.assertNotIn("Access-Control-Allow-Credentials", res.headers)

        with patch.dict(os.environ, {"APP_ENV": "development", "CORS_ALLOWED_ORIGINS": "*"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "cannot include '\\*'"):
                create_app()
