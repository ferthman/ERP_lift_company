import unittest
from datetime import datetime, timedelta, timezone

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket, Master


class TicketFiltersApiTest(unittest.TestCase):
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
        return res

    def create_ticket(self, payload):
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def test_filters_combined(self):
        payload = {
            "object_name": "Filter Test",
            "lat": 43.0,
            "lon": 76.0,
            "description": "Filters",
        }
        t1_id = self.create_ticket({**payload, "priority": "HIGH"})
        t2_id = self.create_ticket({**payload, "priority": "MEDIUM"})
        t3_id = self.create_ticket({**payload, "priority": "LOW"})

        overdue_time = datetime.now(timezone.utc) - timedelta(minutes=200)
        with SessionLocal() as db:
            masters = db.query(Master).order_by(Master.id).all()
            master_one = masters[0].id
            master_two = masters[1].id
            t1 = db.get(Ticket, t1_id)
            t1.assigned_master_id = None
            t1.status = "NEW"
            t1.created_at = overdue_time
            t1.updated_at = overdue_time
            t1.assigned_at = None
            t2 = db.get(Ticket, t2_id)
            t2.assigned_master_id = master_one
            t2.status = "ASSIGNED"
            t2.created_at = datetime.now(timezone.utc)
            t2.assigned_at = datetime.now(timezone.utc)
            t3 = db.get(Ticket, t3_id)
            t3.assigned_master_id = master_two
            t3.status = "ASSIGNED"
            t3.created_at = overdue_time
            t3.assigned_at = overdue_time + timedelta(minutes=10)
            db.commit()

        overdue_res = self.client.get("/api/tickets?overdue=1")
        self.assertEqual(overdue_res.status_code, 200)
        overdue_ids = {t["id"] for t in overdue_res.get_json()}
        self.assertTrue({t1_id, t3_id}.issubset(overdue_ids))
        self.assertNotIn(t2_id, overdue_ids)

        unassigned_res = self.client.get("/api/tickets?unassigned=1")
        self.assertEqual(unassigned_res.status_code, 200)
        unassigned_ids = {t["id"] for t in unassigned_res.get_json()}
        self.assertIn(t1_id, unassigned_ids)
        self.assertNotIn(t2_id, unassigned_ids)
        self.assertNotIn(t3_id, unassigned_ids)

        master_res = self.client.get(f"/api/tickets?master_id={master_one}")
        self.assertEqual(master_res.status_code, 200)
        master_ids = {t["id"] for t in master_res.get_json()}
        self.assertIn(t2_id, master_ids)

        combined_res = self.client.get("/api/tickets?overdue=1&priority=LOW")
        self.assertEqual(combined_res.status_code, 200)
        combined_ids = {t["id"] for t in combined_res.get_json()}
        self.assertIn(t3_id, combined_ids)
        self.assertNotIn(t1_id, combined_ids)
        self.assertNotIn(t2_id, combined_ids)
