import json
import unittest

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket, Master, AuditLog


class AuditLogApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        self.client = self.app.test_client()

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def logout(self):
        self.client.post("/api/logout")

    def create_ticket(self, object_name="Audit Test Object"):
        payload = {
            "object_name": object_name,
            "lat": 43.238949,
            "lon": 76.889709,
            "description": "Audit log test ticket",
        }
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def _master_id(self):
        with SessionLocal() as db:
            master = db.query(Master).order_by(Master.id).first()
            return master.id

    def test_ticket_create_assign_archive_cancel_logs(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        master_id = self._master_id()
        res = self.client.post(f"/api/tickets/{ticket_id}/assign/{master_id}")
        self.assertEqual(res.status_code, 200)
        archive = self.client.post(f"/api/tickets/{ticket_id}/archive")
        self.assertEqual(archive.status_code, 200)

        ticket_id_cancel = self.create_ticket(object_name="Audit Cancel Ticket")
        cancel = self.client.post(
            f"/api/tickets/{ticket_id_cancel}/cancel",
            json={"close_reason": "OTHER", "close_comment": "Nope nope"},
        )
        self.assertEqual(cancel.status_code, 200)
        self.logout()

        with SessionLocal() as db:
            create_log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_type == "ticket", AuditLog.entity_id == ticket_id, AuditLog.action == "CREATE")
                .first()
            )
            self.assertIsNotNone(create_log)
            assign_log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_type == "ticket", AuditLog.entity_id == ticket_id, AuditLog.action == "ASSIGN")
                .first()
            )
            self.assertIsNotNone(assign_log)
            archive_log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_type == "ticket", AuditLog.entity_id == ticket_id, AuditLog.action == "ARCHIVE")
                .first()
            )
            self.assertIsNotNone(archive_log)
            cancel_log = (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_type == "ticket",
                    AuditLog.entity_id == ticket_id_cancel,
                    AuditLog.action == "CANCEL",
                )
                .first()
            )
            self.assertIsNotNone(cancel_log)

            diff = json.loads(assign_log.diff_json or "{}")
            self.assertIn("old", diff)
            self.assertIn("new", diff)
            self.assertIn("assigned_master_id", diff["new"])

    def test_status_change_and_history_permissions(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket(object_name="Audit Status Ticket")
        master_id = self._master_id()
        res = self.client.post(f"/api/tickets/{ticket_id}/assign/{master_id}")
        self.assertEqual(res.status_code, 200)
        self.logout()

        self.login("master1", config.MASTER_PASSWORD)
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

        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        history = self.client.get(f"/api/tickets/{ticket_id}/history")
        self.assertEqual(history.status_code, 200)
        history_data = history.get_json()
        self.assertGreaterEqual(len(history_data), 1)
        created_at_values = [item["created_at"] for item in history_data]
        self.assertEqual(created_at_values, sorted(created_at_values, reverse=True))
        self.logout()

        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        other_ticket_id = self.create_ticket(object_name="Audit Other Ticket")
        master_id = self._master_id()
        res = self.client.post(f"/api/tickets/{other_ticket_id}/assign/{master_id}")
        self.assertEqual(res.status_code, 200)
        self.logout()

        self.login("master2", config.MASTER_PASSWORD)
        forbidden = self.client.get(f"/api/tickets/{other_ticket_id}/history")
        self.assertIn(forbidden.status_code, (401, 403))
        self.logout()

        with SessionLocal() as db:
            status_logs = (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_type == "ticket",
                    AuditLog.entity_id == ticket_id,
                    AuditLog.action == "STATUS_CHANGE",
                )
                .all()
            )
            statuses = []
            for log in status_logs:
                diff = json.loads(log.diff_json or "{}")
                new_status = (diff.get("new") or {}).get("status")
                if new_status:
                    statuses.append(new_status)
            self.assertIn("IN_PROGRESS", statuses)
            self.assertIn("COMPLETED", statuses)
