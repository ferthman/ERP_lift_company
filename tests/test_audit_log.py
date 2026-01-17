import json
import unittest

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket, Master, AuditLog, User
from liftcrm.utils.users import ROLE_TECHNICIAN


class AuditLogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        self.client = self.app.test_client()
        self.master_password = "test-master-pass"
        self._ensure_technician_user("master1", self.master_password, idx=1)
        self._ensure_technician_user("master2", self.master_password, idx=2)

    def _ensure_technician_user(self, username, password, idx=1):
        with SessionLocal() as db:
            master = db.query(Master).order_by(Master.id).offset(idx - 1).first()
            if not master:
                master = Master(name=f"Мастер {idx}", is_active=1)
                db.add(master)
                db.commit()
                db.refresh(master)
            user = db.query(User).filter(User.username == username).first()
            if not user:
                user = User(
                    username=username,
                    password_hash=generate_password_hash(password),
                    role=ROLE_TECHNICIAN,
                    master_id=master.id,
                )
                db.add(user)
            else:
                user.password_hash = generate_password_hash(password)
                user.role = ROLE_TECHNICIAN
                user.master_id = master.id
            db.commit()

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)

    def logout(self):
        self.client.post("/api/logout")

    def create_ticket(self, description="Audit test"):
        payload = {
            "object_name": "Audit Test Object",
            "lat": 43.238949,
            "lon": 76.889709,
            "description": description,
        }
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def _master_id(self, idx=1):
        with SessionLocal() as db:
            master = db.query(Master).order_by(Master.id).offset(idx - 1).first()
            return master.id

    def _audit_entries(self, ticket_id, action):
        with SessionLocal() as db:
            return (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_type == "ticket",
                    AuditLog.entity_id == ticket_id,
                    AuditLog.action == action,
                )
                .all()
            )

    def test_ticket_create_audit(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        self.logout()

        entries = self._audit_entries(ticket_id, "CREATE")
        self.assertEqual(len(entries), 1)
        payload = json.loads(entries[0].diff_json)
        self.assertEqual(payload["old"], {})
        self.assertIn("object_name", payload["new"])
        self.assertIn("status", payload["new"])

    def test_assign_audit(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        master_id = self._master_id()
        res = self.client.post(f"/api/tickets/{ticket_id}/assign/{master_id}")
        self.assertEqual(res.status_code, 200)
        self.logout()

        entries = self._audit_entries(ticket_id, "ASSIGN")
        self.assertTrue(entries)
        payload = json.loads(entries[-1].diff_json)
        self.assertIn("assigned_master_id", payload["new"])
        self.assertIn("status", payload["new"])

    def test_status_change_audit(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        master_id = self._master_id()
        self.client.post(f"/api/tickets/{ticket_id}/assign/{master_id}")
        self.logout()

        self.login("master1", self.master_password)
        arrive = self.client.post(
            f"/api/tickets/{ticket_id}/arrive",
            json={"lat": 43.238949, "lon": 76.889709},
        )
        self.assertEqual(arrive.status_code, 200)
        complete = self.client.post(
            f"/api/tickets/{ticket_id}/complete",
            json={"lat": 43.238949, "lon": 76.889709, "close_reason": "OTHER"},
        )
        self.assertEqual(complete.status_code, 200)
        self.logout()

        entries = self._audit_entries(ticket_id, "STATUS_CHANGE")
        self.assertGreaterEqual(len(entries), 2)
        payload = json.loads(entries[-1].diff_json)
        self.assertIn("status", payload["new"])

    def test_archive_cancel_audit(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        res = self.client.post(f"/api/tickets/{ticket_id}/archive")
        self.assertEqual(res.status_code, 200)
        entries = self._audit_entries(ticket_id, "ARCHIVE")
        self.assertTrue(entries)

        ticket_id_cancel = self.create_ticket(description="Cancel Audit test")
        res = self.client.post(
            f"/api/tickets/{ticket_id_cancel}/cancel",
            json={"close_reason": "OTHER", "close_comment": "Cancel audit reason"},
        )
        self.assertEqual(res.status_code, 200)
        cancel_entries = self._audit_entries(ticket_id_cancel, "CANCEL")
        self.assertTrue(cancel_entries)
        payload = json.loads(cancel_entries[-1].diff_json)
        self.assertIn("close_reason", payload["new"])
        self.assertIn("close_comment", payload["new"])
        self.logout()

    def test_history_rbac(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        master_id = self._master_id()
        self.client.post(f"/api/tickets/{ticket_id}/assign/{master_id}")
        self.logout()

        self.login("master2", self.master_password)
        res = self.client.get(f"/api/tickets/{ticket_id}/history")
        self.assertEqual(res.status_code, 403)
        self.logout()

        self.login("master1", self.master_password)
        res = self.client.get(f"/api/tickets/{ticket_id}/history")
        self.assertEqual(res.status_code, 200)
        self.logout()

    def test_history_on_archived_ticket(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        self.client.post(f"/api/tickets/{ticket_id}/archive")
        res = self.client.get(f"/api/tickets/{ticket_id}/history")
        self.assertEqual(res.status_code, 200)
        self.logout()
