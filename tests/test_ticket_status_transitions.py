import unittest

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket, Master
from liftcrm.tickets.service import validate_status_transition


class TicketStatusTransitionTest(unittest.TestCase):
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

    def create_ticket(self):
        payload = {
            "object_name": "Transition Test Object",
            "lat": 43.238949,
            "lon": 76.889709,
            "description": "Transition test ticket",
        }
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def _master_id(self):
        with SessionLocal() as db:
            master = db.query(Master).order_by(Master.id).first()
            return master.id

    def test_invalid_transition_new_to_completed(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        master_id = self._master_id()
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            ticket.assigned_master_id = master_id
            ticket.status = "NEW"
            db.commit()
        self.logout()

        self.login("master1", config.MASTER_PASSWORD)
        res = self.client.post(
            f"/api/tickets/{ticket_id}/complete",
            json={"lat": 43.238949, "lon": 76.889709, "close_reason": "OTHER"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])

    def test_assigned_requires_assigned_master_id(self):
        ticket = Ticket(status="NEW")
        ok, code, message = validate_status_transition("NEW", "ASSIGNED", ticket, "admin", {})
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_STATUS_TRANSITION")
        self.assertIn("assigned_master_id", message)

    def test_assigned_to_in_progress_requires_assigned_master_id(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            ticket.status = "ASSIGNED"
            ticket.assigned_master_id = None
            db.commit()
        self.logout()

        self.login("master1", config.MASTER_PASSWORD)
        res = self.client.post(
            f"/api/tickets/{ticket_id}/arrive",
            json={"lat": 43.238949, "lon": 76.889709},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])

    def test_in_progress_to_completed_requires_completed_at(self):
        ticket = Ticket(status="IN_PROGRESS")
        ok, code, message = validate_status_transition("IN_PROGRESS", "COMPLETED", ticket, "admin", {})
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_STATUS_TRANSITION")
        self.assertIn("completed_at", message)

    def test_cancel_permissions_and_validation(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        self.logout()

        self.login("master1", config.MASTER_PASSWORD)
        res = self.client.post(
            f"/api/tickets/{ticket_id}/cancel",
            json={"close_reason": "DUPLICATE", "close_comment": "Нет доступа"},
        )
        self.assertIn(res.status_code, (401, 403))
        self.logout()

        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        res = self.client.post(f"/api/tickets/{ticket_id}/cancel", json={})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")

        res = self.client.post(
            f"/api/tickets/{ticket_id}/cancel",
            json={"close_reason": "INVALID", "close_comment": "Нет доступа"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")

        res = self.client.post(
            f"/api/tickets/{ticket_id}/cancel",
            json={"close_reason": "NO_ACCESS", "close_comment": "мало"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")

        res = self.client.post(
            f"/api/tickets/{ticket_id}/cancel",
            json={"close_reason": "NO_ACCESS", "close_comment": "Нет доступа к объекту"},
        )
        self.assertEqual(res.status_code, 200)

        res = self.client.get(f"/api/tickets/{ticket_id}")
        data = res.get_json()
        self.assertEqual(data["status"], "CANCELLED")
        self.assertEqual(data["close_reason"], "NO_ACCESS")
        self.assertEqual(data["close_comment"], "Нет доступа к объекту")

    def test_happy_path_assign_arrive_complete(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
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
        res = self.client.get(f"/api/tickets/{ticket_id}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertIsNotNone(data["completed_at"])

    def test_archived_immutability_on_state_changes(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        master_id = self._master_id()
        self.client.post(f"/api/tickets/{ticket_id}/assign/{master_id}")
        res = self.client.post(f"/api/tickets/{ticket_id}/archive")
        self.assertEqual(res.status_code, 200)
        self.logout()

        self.login("master1", config.MASTER_PASSWORD)
        arrive = self.client.post(
            f"/api/tickets/{ticket_id}/arrive",
            json={"lat": 43.238949, "lon": 76.889709},
        )
        self.assertEqual(arrive.status_code, 400)
        complete = self.client.post(
            f"/api/tickets/{ticket_id}/complete",
            json={"lat": 43.238949, "lon": 76.889709, "close_reason": "OTHER"},
        )
        self.assertEqual(complete.status_code, 400)
        self.logout()

        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        cancel = self.client.post(
            f"/api/tickets/{ticket_id}/cancel",
            json={"close_reason": "OTHER", "close_comment": "Archive test reason"},
        )
        self.assertEqual(cancel.status_code, 400)
