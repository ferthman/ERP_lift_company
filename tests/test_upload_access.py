import importlib
import os
import tempfile
import unittest
import uuid

from liftcrm import config, create_app


class UploadAccessTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        self.original_archive_path = config.ARCHIVE_PATH
        self.original_upload_folder = config.UPLOAD_FOLDER
        config.DB_PATH = os.path.join(self.tmpdir.name, "uploads.db")
        config.ARCHIVE_PATH = os.path.join(self.tmpdir.name, "archive.xlsx")
        config.UPLOAD_FOLDER = os.path.join(self.tmpdir.name, "uploads")
        self._reload_db_bound_modules()

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.client.get("/")
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        self._create_fixture()

    def tearDown(self):
        self.client.post("/api/logout")
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
            try:
                module = importlib.import_module(name)
                importlib.reload(module)
            except Exception:
                continue

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)

    def logout(self):
        self.client.post("/api/logout")

    def _create_master_and_technician(self, label):
        res = self.client.post("/api/masters", json={"name": f"Upload Master {label}"})
        self.assertEqual(res.status_code, 201)
        master_id = res.get_json()["id"]
        role_res = self.client.post(
            f"/api/masters/{master_id}/assign-role",
            json={"role": "TECHNICIAN", "username": f"upload_tech_{label}"},
        )
        self.assertEqual(role_res.status_code, 200)
        payload = role_res.get_json()
        return master_id, payload["username"], payload["temp_password"]

    def _create_fixture(self):
        from liftcrm.db import Attachment, SessionLocal, Ticket

        label = uuid.uuid4().hex[:8]
        self.master_one, self.tech_one, self.tech_one_password = self._create_master_and_technician(
            f"{label}_one"
        )
        self.master_two, self.tech_two, self.tech_two_password = self._create_master_and_technician(
            f"{label}_two"
        )
        self.assigned_filename = f"{label}_assigned.jpg"
        self.other_filename = f"{label}_other.jpg"
        with SessionLocal() as db:
            assigned_ticket = Ticket(
                object_name="Assigned upload ticket",
                lat=43.2,
                lon=76.9,
                status="IN_PROGRESS",
                assigned_master_id=self.master_one,
            )
            other_ticket = Ticket(
                object_name="Other upload ticket",
                lat=43.3,
                lon=77.0,
                status="IN_PROGRESS",
                assigned_master_id=self.master_two,
            )
            db.add_all([assigned_ticket, other_ticket])
            db.flush()
            db.add_all(
                [
                    Attachment(
                        ticket_id=assigned_ticket.id,
                        filename=self.assigned_filename,
                        orig_name="assigned.jpg",
                    ),
                    Attachment(
                        ticket_id=other_ticket.id,
                        filename=self.other_filename,
                        orig_name="other.jpg",
                    ),
                ]
            )
            db.commit()

        os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
        with open(os.path.join(config.UPLOAD_FOLDER, self.assigned_filename), "wb") as file_obj:
            file_obj.write(b"assigned-upload")
        with open(os.path.join(config.UPLOAD_FOLDER, self.other_filename), "wb") as file_obj:
            file_obj.write(b"other-upload")

    def test_anonymous_user_cannot_access_upload(self):
        self.logout()

        res = self.client.get(f"/uploads/{self.assigned_filename}")

        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

    def test_unrelated_technician_cannot_access_another_ticket_upload(self):
        self.logout()
        self.login(self.tech_two, self.tech_two_password)

        res = self.client.get(f"/uploads/{self.assigned_filename}")

        self.assertEqual(res.status_code, 403)

    def test_assigned_technician_can_access_own_ticket_upload(self):
        self.logout()
        self.login(self.tech_one, self.tech_one_password)

        res = self.client.get(f"/uploads/{self.assigned_filename}")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, b"assigned-upload")

    def test_admin_can_access_upload(self):
        res = self.client.get(f"/uploads/{self.assigned_filename}")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, b"assigned-upload")

    def test_dispatcher_can_access_operational_upload(self):
        self.logout()
        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)

        res = self.client.get(f"/uploads/{self.assigned_filename}")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, b"assigned-upload")

    def test_unsafe_filename_access_is_rejected(self):
        res = self.client.get(f"/uploads/%2e%2e/{self.assigned_filename}")

        self.assertEqual(res.status_code, 404)
