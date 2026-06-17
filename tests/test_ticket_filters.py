import unittest
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket, Master, Asset


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

    def test_status_search_date_and_asset_filters(self):
        token = uuid4().hex[:8]
        asset_res = self.client.post(
            "/api/assets",
            json={
                "address": f"Алматы фильтр asset {token}",
                "serial_no": f"FILTER-{token}",
                "lift_label": f"Лифт {token}",
                "lat": 43.31,
                "lon": 76.91,
            },
        )
        self.assertEqual(asset_res.status_code, 201)
        asset_id = asset_res.get_json()["id"]

        first_id = self.create_ticket(
            {
                "object_name": f"Search Alpha {token}",
                "asset_id": asset_id,
                "description": f"Unique filter text {token}",
                "problem_type": "DOORS",
            }
        )
        second_id = self.create_ticket(
            {
                "object_name": f"Search Beta {token}",
                "lat": 43.4,
                "lon": 76.7,
                "description": "Other ticket",
            }
        )

        with SessionLocal() as db:
            first = db.get(Ticket, first_id)
            first.status = "WAITING"
            first.created_at = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
            first.updated_at = first.created_at
            second = db.get(Ticket, second_id)
            second.status = "NEW"
            second.created_at = datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc)
            second.updated_at = second.created_at
            db.commit()

        status_res = self.client.get("/api/tickets?status=WAITING")
        self.assertEqual(status_res.status_code, 200)
        status_ids = {item["id"] for item in status_res.get_json()}
        self.assertIn(first_id, status_ids)
        self.assertNotIn(second_id, status_ids)

        q_res = self.client.get(f"/api/tickets?q={token}")
        self.assertEqual(q_res.status_code, 200)
        q_ids = {item["id"] for item in q_res.get_json()}
        self.assertIn(first_id, q_ids)

        date_res = self.client.get("/api/tickets?date_from=2026-01-01&date_to=2026-01-31")
        self.assertEqual(date_res.status_code, 200)
        date_ids = {item["id"] for item in date_res.get_json()}
        self.assertIn(first_id, date_ids)
        self.assertNotIn(second_id, date_ids)

        asset_filter_res = self.client.get(f"/api/tickets?asset_id={asset_id}")
        self.assertEqual(asset_filter_res.status_code, 200)
        asset_ids = {item["id"] for item in asset_filter_res.get_json()}
        self.assertIn(first_id, asset_ids)
        self.assertNotIn(second_id, asset_ids)

        invalid_status = self.client.get("/api/tickets?status=BAD")
        self.assertEqual(invalid_status.status_code, 400)
        invalid_date = self.client.get("/api/tickets?date_from=bad-date")
        self.assertEqual(invalid_date.status_code, 400)
        invalid_asset = self.client.get("/api/tickets?asset_id=bad")
        self.assertEqual(invalid_asset.status_code, 400)

    def test_problem_type_create_update_clear_and_validation(self):
        created_id = self.create_ticket(
            {
                "object_name": "Problem Type Test",
                "lat": 43.0,
                "lon": 76.0,
                "description": "Doors issue",
                "problem_type": "DOORS",
            }
        )

        detail = self.client.get(f"/api/tickets/{created_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["problem_type"], "DOORS")

        update = self.client.patch(f"/api/tickets/{created_id}", json={"problem_type": "POWER"})
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json()["problem_type"], "POWER")

        clear = self.client.patch(f"/api/tickets/{created_id}", json={"problem_type": ""})
        self.assertEqual(clear.status_code, 200)
        self.assertIsNone(clear.get_json()["problem_type"])

        bad_create = self.client.post(
            "/api/tickets",
            json={"object_name": "Bad problem", "lat": 43.0, "lon": 76.0, "problem_type": "BAD"},
        )
        self.assertEqual(bad_create.status_code, 400)

        bad_update = self.client.patch(f"/api/tickets/{created_id}", json={"problem_type": "BAD"})
        self.assertEqual(bad_update.status_code, 400)
