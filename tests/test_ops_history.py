import unittest
import uuid
from datetime import datetime, timedelta, timezone

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket


class OpsHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        self.client = self.app.test_client()
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)

    def logout(self):
        self.client.post("/api/logout")

    def create_ticket(self, payload):
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def test_ops_limit_completed_cancelled(self):
        payload = {
            "object_name": "История лимит",
            "lat": 43.0,
            "lon": 76.0,
            "description": "Ops",
        }
        master_res = self.client.post("/api/masters", json={"name": f"История мастер {uuid.uuid4().hex[:6]}"})
        self.assertEqual(master_res.status_code, 201)
        master_id = master_res.get_json()["id"]
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        completed_ids = []
        cancelled_ids = []
        for idx in range(5):
            completed_ids.append(self.create_ticket({**payload, "object_name": f"Completed {idx}"}))
            cancelled_ids.append(self.create_ticket({**payload, "object_name": f"Cancelled {idx}"}))

        with SessionLocal() as db:
            for idx, ticket_id in enumerate(completed_ids):
                ticket = db.get(Ticket, ticket_id)
                ticket.status = "COMPLETED"
                ticket.completed_at = base_time + timedelta(days=idx)
                ticket.updated_at = ticket.completed_at
                ticket.assigned_master_id = master_id
                ticket.assigned_at = base_time
            for idx, ticket_id in enumerate(cancelled_ids):
                ticket = db.get(Ticket, ticket_id)
                ticket.status = "CANCELLED"
                ticket.cancelled_at = base_time + timedelta(days=idx)
                ticket.updated_at = base_time + timedelta(days=30 - idx)
                ticket.assigned_master_id = master_id
                ticket.assigned_at = base_time
            db.commit()

        res = self.client.get(f"/api/tickets?kanban=1&master_id={master_id}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        completed_returned = [t["id"] for t in data if t["status"] == "COMPLETED"]
        cancelled_returned = [t["id"] for t in data if t["status"] == "CANCELLED"]

        expected_completed = set(completed_ids[1:])
        expected_cancelled = set(cancelled_ids[1:])
        self.assertEqual(set(completed_returned), expected_completed)
        self.assertEqual(set(cancelled_returned), expected_cancelled)

    def test_history_date_filtering(self):
        payload = {
            "object_name": "История фильтр",
            "lat": 43.2,
            "lon": 76.2,
            "description": "Дата",
        }
        completed_early = self.create_ticket({**payload, "object_name": "Completed Early"})
        completed_mid = self.create_ticket({**payload, "object_name": "Completed Mid"})
        completed_late = self.create_ticket({**payload, "object_name": "Completed Late"})
        cancelled_mid = self.create_ticket({**payload, "object_name": "Cancelled Mid"})

        with SessionLocal() as db:
            t_early = db.get(Ticket, completed_early)
            t_early.status = "COMPLETED"
            t_early.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            t_early.updated_at = t_early.completed_at

            t_mid = db.get(Ticket, completed_mid)
            t_mid.status = "COMPLETED"
            t_mid.completed_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
            t_mid.updated_at = t_mid.completed_at

            t_late = db.get(Ticket, completed_late)
            t_late.status = "COMPLETED"
            t_late.completed_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
            t_late.updated_at = t_late.completed_at

            t_cancelled = db.get(Ticket, cancelled_mid)
            t_cancelled.status = "CANCELLED"
            t_cancelled.cancelled_at = datetime(2026, 1, 20, tzinfo=timezone.utc)
            t_cancelled.updated_at = datetime(2026, 2, 20, tzinfo=timezone.utc)

            db.commit()

        res = self.client.get(
            "/api/tickets/history?date_from=2026-01-10&date_to=2026-01-31&statuses=COMPLETED,CANCELLED"
        )
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["items"]
        ids = {item["id"] for item in items}
        self.assertIn(completed_mid, ids)
        self.assertIn(cancelled_mid, ids)
        self.assertNotIn(completed_early, ids)
        self.assertNotIn(completed_late, ids)

    def test_cancelled_at_stable_after_edit(self):
        payload = {
            "object_name": "История отмены",
            "lat": 43.3,
            "lon": 76.3,
            "description": "Отмена",
        }
        ticket_id = self.create_ticket(payload)
        cancel_res = self.client.post(
            f"/api/tickets/{ticket_id}/cancel",
            json={"close_reason": "CUSTOMER_CANCELLED", "close_comment": "Client cancelled"},
        )
        self.assertEqual(cancel_res.status_code, 200)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            initial_cancelled_at = ticket.cancelled_at
            self.assertIsNotNone(initial_cancelled_at)
        edit_res = self.client.patch(
            f"/api/tickets/{ticket_id}",
            json={"description": "Updated after cancel"},
        )
        self.assertEqual(edit_res.status_code, 200)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.cancelled_at, initial_cancelled_at)

    def test_history_rbac(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        master_name = f"Мастер {uuid.uuid4().hex[:6]}"
        res = self.client.post("/api/masters", json={"name": master_name})
        self.assertEqual(res.status_code, 201)
        master_id = res.get_json()["id"]
        res = self.client.post(
            f"/api/masters/{master_id}/assign-role",
            json={"role": "TECHNICIAN", "username": f"tech_{uuid.uuid4().hex[:6]}"},
        )
        self.assertEqual(res.status_code, 200)
        tech_username = res.get_json()["username"]
        tech_password = res.get_json()["temp_password"]

        self.logout()
        self.login(tech_username, tech_password)

        page_res = self.client.get("/history")
        api_res = self.client.get("/api/tickets/history")
        self.assertEqual(page_res.status_code, 403)
        self.assertEqual(api_res.status_code, 403)
