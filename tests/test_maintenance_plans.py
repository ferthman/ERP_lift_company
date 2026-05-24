import unittest
from datetime import date, timedelta
from uuid import uuid4

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Asset, MaintenancePlan, Master, Ticket, User
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

    def create_plan_row(self, *, asset_id, title, due_date, status="active", master_id=None):
        with SessionLocal() as db:
            plan = MaintenancePlan(
                asset_id=asset_id,
                title=title,
                description=f"{title} description",
                interval_type="monthly",
                next_due_date=due_date,
                assigned_master_id=master_id,
                status=status,
                notes=f"{title} notes",
            )
            db.add(plan)
            db.commit()
            db.refresh(plan)
            return plan.id

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

    def test_due_queue_groups_overdue_today_and_upcoming_active_plans(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        asset_id, master_id = self.create_asset_and_master()
        token = uuid4().hex[:8]
        today = date.today()
        expected = {
            "overdue": self.create_plan_row(
                asset_id=asset_id,
                master_id=master_id,
                title=f"overdue-{token}",
                due_date=today - timedelta(days=1),
            ),
            "today": self.create_plan_row(
                asset_id=asset_id,
                master_id=master_id,
                title=f"today-{token}",
                due_date=today,
            ),
            "next_7_days": self.create_plan_row(
                asset_id=asset_id,
                master_id=master_id,
                title=f"week-{token}",
                due_date=today + timedelta(days=7),
            ),
            "next_30_days": self.create_plan_row(
                asset_id=asset_id,
                master_id=master_id,
                title=f"month-{token}",
                due_date=today + timedelta(days=30),
            ),
        }

        res = self.client.get("/api/maintenance-plans/due")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        by_id = {item["id"]: item for item in data["plans"] if item["id"] in expected.values()}

        self.assertEqual(by_id[expected["overdue"]]["due_status"], "overdue")
        self.assertEqual(by_id[expected["overdue"]]["due_bucket"], "overdue")
        self.assertEqual(by_id[expected["today"]]["due_bucket"], "today")
        self.assertEqual(by_id[expected["next_7_days"]]["due_bucket"], "next_7_days")
        self.assertEqual(by_id[expected["next_30_days"]]["due_bucket"], "next_30_days")
        self.assertGreaterEqual(data["counters"]["overdue"], 1)
        self.assertGreaterEqual(data["counters"]["today"], 1)
        self.assertGreaterEqual(data["counters"]["next_7_days"], 1)
        self.assertGreaterEqual(data["counters"]["next_30_days"], 1)

    def test_due_queue_keeps_paused_and_completed_out_of_active_queue_by_default(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        asset_id, _ = self.create_asset_and_master()
        token = uuid4().hex[:8]
        today = date.today()
        paused_id = self.create_plan_row(
            asset_id=asset_id,
            title=f"paused-{token}",
            due_date=today,
            status="paused",
        )
        completed_id = self.create_plan_row(
            asset_id=asset_id,
            title=f"completed-{token}",
            due_date=today,
            status="completed",
        )

        default_res = self.client.get("/api/maintenance-plans/due")
        self.assertEqual(default_res.status_code, 200)
        default_data = default_res.get_json()
        active_ids = {item["id"] for item in default_data["plans"]}
        inactive_ids = {item["id"] for item in default_data["inactive_plans"]}
        self.assertNotIn(paused_id, active_ids)
        self.assertNotIn(completed_id, active_ids)
        self.assertNotIn(paused_id, inactive_ids)
        self.assertNotIn(completed_id, inactive_ids)

        included_res = self.client.get("/api/maintenance-plans/due?include_inactive=1")
        self.assertEqual(included_res.status_code, 200)
        included_inactive_ids = {item["id"] for item in included_res.get_json()["inactive_plans"]}
        self.assertIn(paused_id, included_inactive_ids)
        self.assertIn(completed_id, included_inactive_ids)

    def test_due_queue_filters_by_date_status_master_and_overdue_only(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        asset_id, master_id = self.create_asset_and_master()
        _, other_master_id = self.create_asset_and_master()
        token = uuid4().hex[:8]
        today = date.today()
        overdue_id = self.create_plan_row(
            asset_id=asset_id,
            master_id=master_id,
            title=f"filter-overdue-{token}",
            due_date=today - timedelta(days=2),
        )
        in_range_id = self.create_plan_row(
            asset_id=asset_id,
            master_id=master_id,
            title=f"filter-range-{token}",
            due_date=today + timedelta(days=5),
        )
        other_master_plan_id = self.create_plan_row(
            asset_id=asset_id,
            master_id=other_master_id,
            title=f"filter-other-master-{token}",
            due_date=today + timedelta(days=5),
        )

        range_res = self.client.get(
            f"/api/maintenance-plans/due?date_from={today.isoformat()}&date_to={(today + timedelta(days=7)).isoformat()}"
        )
        self.assertEqual(range_res.status_code, 200)
        range_ids = {item["id"] for item in range_res.get_json()["plans"]}
        self.assertIn(in_range_id, range_ids)
        self.assertNotIn(overdue_id, range_ids)

        master_res = self.client.get(f"/api/maintenance-plans/due?assigned_master_id={master_id}")
        self.assertEqual(master_res.status_code, 200)
        master_ids = {item["id"] for item in master_res.get_json()["plans"]}
        self.assertIn(in_range_id, master_ids)
        self.assertNotIn(other_master_plan_id, master_ids)

        overdue_res = self.client.get("/api/maintenance-plans/due?overdue_only=1")
        self.assertEqual(overdue_res.status_code, 200)
        overdue_ids = {item["id"] for item in overdue_res.get_json()["plans"]}
        self.assertIn(overdue_id, overdue_ids)
        self.assertNotIn(in_range_id, overdue_ids)

        status_res = self.client.get("/api/maintenance-plans/due?status=overdue")
        self.assertEqual(status_res.status_code, 200)
        status_ids = {item["id"] for item in status_res.get_json()["plans"]}
        self.assertIn(overdue_id, status_ids)

    def test_due_queue_access_rules_match_maintenance_management(self):
        username, password = self.create_technician()

        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        dispatcher_res = self.client.get("/api/maintenance-plans/due")
        self.assertEqual(dispatcher_res.status_code, 200)

        tech_client = self.app.test_client()
        tech_login = tech_client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(tech_login.status_code, 200)
        forbidden = tech_client.get("/api/maintenance-plans/due")
        self.assertEqual(forbidden.status_code, 403)

        anonymous = self.app.test_client().get("/api/maintenance-plans/due")
        self.assertEqual(anonymous.status_code, 401)

    def test_generate_ticket_from_due_plan_links_ticket_and_prevents_duplicates(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        asset_id, master_id = self.create_asset_and_master()
        today = date.today()
        plan_id = self.create_plan_row(
            asset_id=asset_id,
            master_id=master_id,
            title=f"ticket-plan-{uuid4().hex[:8]}",
            due_date=today,
        )

        created = self.client.post(f"/api/maintenance-plans/{plan_id}/generate-ticket", json={})
        self.assertEqual(created.status_code, 201)
        created_data = created.get_json()
        self.assertFalse(created_data["duplicate"])
        ticket_id = created_data["ticket_id"]

        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.maintenance_plan_id, plan_id)
            self.assertEqual(ticket.maintenance_due_date, today)
            self.assertEqual(ticket.asset_id, asset_id)
            self.assertEqual(ticket.priority, "MEDIUM")
            self.assertIn("Плановое ТО:", ticket.description)
            self.assertEqual(ticket.assigned_master_id, master_id)

        duplicate = self.client.post(f"/api/maintenance-plans/{plan_id}/generate-ticket", json={})
        self.assertEqual(duplicate.status_code, 200)
        duplicate_data = duplicate.get_json()
        self.assertTrue(duplicate_data["duplicate"])
        self.assertEqual(duplicate_data["ticket_id"], ticket_id)

    def test_generate_ticket_rejects_inactive_plan_and_plan_without_asset_coordinates(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        token = uuid4().hex[:8]
        with SessionLocal() as db:
            asset = Asset(
                address=f"Алматы, без координат {token}",
                address_norm=f"алматы без координат {token}",
                lift_label="Лифт B",
                serial_no=f"PM-NOCOORD-{token}",
                status="ACTIVE",
            )
            db.add(asset)
            db.commit()
            db.refresh(asset)
            asset_id = asset.id
        paused_id = self.create_plan_row(
            asset_id=asset_id,
            title=f"paused-ticket-{token}",
            due_date=date.today(),
            status="paused",
        )
        active_id = self.create_plan_row(
            asset_id=asset_id,
            title=f"coord-ticket-{token}",
            due_date=date.today(),
        )

        inactive = self.client.post(f"/api/maintenance-plans/{paused_id}/generate-ticket", json={})
        self.assertEqual(inactive.status_code, 400)

        no_coords = self.client.post(f"/api/maintenance-plans/{active_id}/generate-ticket", json={})
        self.assertEqual(no_coords.status_code, 400)
