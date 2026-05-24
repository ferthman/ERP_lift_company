import unittest
from uuid import uuid4

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Asset, MaintenancePlan, Master, User
from liftcrm.utils.rate_limit import clear_rate_limits


class MaintenancePlansTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        clear_rate_limits()
        self.client = self.app.test_client()

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def create_asset_and_master(self):
        token = uuid4().hex[:8]
        with SessionLocal() as db:
            asset = Asset(
                address=f"Алматы, ТО {token}",
                address_norm=f"алматы то {token}",
                lift_label="Лифт A",
                serial_no=f"PM-{token}",
                lat=43.2,
                lon=76.9,
                status="ACTIVE",
            )
            master = Master(name=f"ТО мастер {token}", is_active=1)
            db.add_all([asset, master])
            db.commit()
            db.refresh(asset)
            db.refresh(master)
            return asset.id, master.id

    def create_technician(self):
        token = uuid4().hex[:8]
        password = "tech-pass"
        with SessionLocal() as db:
            master = Master(name=f"Техник ТО {token}", is_active=1)
            db.add(master)
            db.flush()
            user = User(
                username=f"tech_pm_{token}",
                password_hash=generate_password_hash(password),
                role="technician",
                master_id=master.id,
                is_active=1,
            )
            db.add(user)
            db.commit()
            return user.username, password

    def plan_payload(self, asset_id, master_id=None):
        payload = {
            "asset_id": asset_id,
            "title": "Ежемесячное ТО",
            "description": "Проверка дверей и шкафа управления",
            "interval_type": "monthly",
            "next_due_date": "2026-06-15",
            "status": "active",
            "notes": "Без генерации заявки",
        }
        if master_id:
            payload["assigned_master_id"] = master_id
        return payload

    def test_admin_can_create_update_list_and_complete_plan(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        asset_id, master_id = self.create_asset_and_master()

        create = self.client.post("/api/maintenance-plans", json=self.plan_payload(asset_id, master_id))
        self.assertEqual(create.status_code, 201)
        created = create.get_json()
        self.assertEqual(created["asset_id"], asset_id)
        self.assertEqual(created["assigned_master_id"], master_id)
        self.assertEqual(created["status"], "active")

        plan_id = created["id"]
        patch = self.client.patch(
            f"/api/maintenance-plans/{plan_id}",
            json={"title": "Квартальное ТО", "interval_type": "quarterly", "next_due_date": "2026-07-01"},
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.get_json()["title"], "Квартальное ТО")

        listed = self.client.get("/api/maintenance-plans")
        self.assertEqual(listed.status_code, 200)
        self.assertIn(plan_id, [item["id"] for item in listed.get_json()])

        complete = self.client.post(
            f"/api/maintenance-plans/{plan_id}/complete",
            json={"completed_date": "2026-07-02"},
        )
        self.assertEqual(complete.status_code, 200)
        data = complete.get_json()
        self.assertEqual(data["last_completed_date"], "2026-07-02")
        self.assertEqual(data["next_due_date"], "2026-10-02")
        self.assertEqual(data["status"], "active")

    def test_dispatcher_can_manage_maintenance_plans(self):
        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        asset_id, _ = self.create_asset_and_master()

        res = self.client.post("/api/maintenance-plans", json=self.plan_payload(asset_id))
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["title"], "Ежемесячное ТО")

    def test_technician_and_anonymous_cannot_manage_plans(self):
        username, password = self.create_technician()
        self.login(username, password)
        asset_id, _ = self.create_asset_and_master()

        forbidden = self.client.post("/api/maintenance-plans", json=self.plan_payload(asset_id))
        self.assertEqual(forbidden.status_code, 403)

        anonymous = self.app.test_client().get("/api/maintenance-plans")
        self.assertEqual(anonymous.status_code, 401)

    def test_invalid_payloads_return_400(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        asset_id, master_id = self.create_asset_and_master()

        cases = [
            {"asset_id": 999999, "title": "ТО", "interval_type": "monthly", "next_due_date": "2026-06-01"},
            {"asset_id": asset_id, "title": "", "interval_type": "monthly", "next_due_date": "2026-06-01"},
            {"asset_id": asset_id, "title": "ТО", "interval_type": "weekly", "next_due_date": "2026-06-01"},
            {"asset_id": asset_id, "title": "ТО", "interval_type": "monthly", "next_due_date": "bad-date"},
            {"asset_id": asset_id, "title": "ТО", "interval_type": "monthly", "next_due_date": "2026-06-01", "status": "bad"},
            {
                "asset_id": asset_id,
                "title": "ТО",
                "interval_type": "monthly",
                "next_due_date": "2026-06-01",
                "assigned_master_id": master_id + 999999,
            },
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                res = self.client.post("/api/maintenance-plans", json=payload)
                self.assertEqual(res.status_code, 400)

    def test_custom_interval_completion_marks_plan_completed_without_auto_next_date(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        asset_id, _ = self.create_asset_and_master()
        payload = self.plan_payload(asset_id)
        payload["interval_type"] = "custom"

        create = self.client.post("/api/maintenance-plans", json=payload)
        self.assertEqual(create.status_code, 201)
        plan_id = create.get_json()["id"]

        complete = self.client.post(
            f"/api/maintenance-plans/{plan_id}/complete",
            json={"completed_date": "2026-06-16"},
        )
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.get_json()["status"], "completed")

        with SessionLocal() as db:
            stored = db.get(MaintenancePlan, plan_id)
            self.assertEqual(stored.last_completed_date.isoformat(), "2026-06-16")

