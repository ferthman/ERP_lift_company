import json
import unittest
import uuid

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import AuditLog, Master, SessionLocal, Ticket, User
from liftcrm.utils.rate_limit import clear_rate_limits
from liftcrm.utils.roles import ROLE_TECHNICIAN


class EmergencyPriorityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        clear_rate_limits()
        self.client = self.app.test_client()
        self.tech_password = "test-tech-pass"
        self.tech_username = f"emergency_tech_{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            master = Master(name=f"Аварийный мастер {self.tech_username}", is_active=1)
            db.add(master)
            db.commit()
            db.refresh(master)
            user = User(
                username=self.tech_username,
                password_hash=generate_password_hash(self.tech_password),
                role=ROLE_TECHNICIAN,
                master_id=master.id,
                is_active=1,
            )
            db.add(user)
            db.commit()
            self.master_id = master.id

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def logout(self):
        self.client.post("/api/logout")

    def ticket_payload(self, **overrides):
        payload = {
            "object_name": f"Emergency Priority {uuid.uuid4().hex[:8]}",
            "address": "Almaty emergency address",
            "lat": 43.238949,
            "lon": 76.889709,
            "description": "Passenger trapped / urgent safety issue",
        }
        payload.update(overrides)
        return payload

    def create_ticket(self, priority="MEDIUM", **overrides):
        payload = self.ticket_payload(priority=priority, **overrides)
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201, res.get_data(as_text=True))
        return res.get_json()

    def test_admin_can_create_emergency_ticket_with_short_sla_defaults(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_ticket(priority="emergency")

        self.assertEqual(created["priority"], "EMERGENCY")
        self.assertEqual(created["custom_sla_response_minutes"], 5)
        self.assertEqual(created["custom_sla_completion_minutes"], 60)

        detail = self.client.get(f"/api/tickets/{created['id']}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        self.assertEqual(payload["priority"], "EMERGENCY")
        self.assertEqual(payload["custom_sla_response_minutes"], 5)
        self.assertEqual(payload["custom_sla_completion_minutes"], 60)

    def test_dispatcher_can_create_high_priority_ticket_and_normal_alias_maps_to_medium(self):
        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        high = self.create_ticket(priority="high")
        normal = self.create_ticket(priority="normal")

        self.assertEqual(high["priority"], "HIGH")
        self.assertEqual(high["custom_sla_response_minutes"], 15)
        self.assertEqual(high["custom_sla_completion_minutes"], 90)
        self.assertEqual(normal["priority"], "MEDIUM")

    def test_technician_cannot_create_emergency_ticket(self):
        self.login(self.tech_username, self.tech_password)
        res = self.client.post("/api/tickets", json=self.ticket_payload(priority="EMERGENCY"))
        self.assertEqual(res.status_code, 403)

    def test_invalid_priority_is_rejected_on_create_update_and_filter(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

        create_res = self.client.post("/api/tickets", json=self.ticket_payload(priority="BLOCKER"))
        self.assertEqual(create_res.status_code, 400)

        created = self.create_ticket(priority="MEDIUM")
        update_res = self.client.patch(f"/api/tickets/{created['id']}", json={"priority": "BLOCKER"})
        self.assertEqual(update_res.status_code, 400)

        filter_res = self.client.get("/api/tickets?priority=BLOCKER")
        self.assertEqual(filter_res.status_code, 400)

    def test_priority_filter_and_emergency_first_sorting(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        normal = self.create_ticket(priority="normal")
        emergency = self.create_ticket(priority="emergency")

        filter_res = self.client.get("/api/tickets?priority=emergency")
        self.assertEqual(filter_res.status_code, 200)
        filtered_ids = {item["id"] for item in filter_res.get_json()}
        self.assertIn(emergency["id"], filtered_ids)
        self.assertNotIn(normal["id"], filtered_ids)

        list_res = self.client.get("/api/tickets")
        self.assertEqual(list_res.status_code, 200)
        ordered_ids = [item["id"] for item in list_res.get_json()]
        self.assertLess(ordered_ids.index(emergency["id"]), ordered_ids.index(normal["id"]))

    def test_mobile_ticket_payload_includes_priority(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_ticket(priority="EMERGENCY")
        assign_res = self.client.post(f"/api/tickets/{created['id']}/assign/{self.master_id}")
        self.assertEqual(assign_res.status_code, 200)
        self.logout()

        self.login(self.tech_username, self.tech_password)
        res = self.client.get("/api/me/tickets")
        self.assertEqual(res.status_code, 200)
        tickets = res.get_json()
        ticket = next(item for item in tickets if item["id"] == created["id"])
        self.assertEqual(ticket["priority"], "EMERGENCY")

    def test_priority_change_is_audit_logged(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_ticket(priority="normal")

        res = self.client.patch(f"/api/tickets/{created['id']}", json={"priority": "emergency"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["priority"], "EMERGENCY")

        with SessionLocal() as db:
            entries = (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_type == "ticket",
                    AuditLog.entity_id == created["id"],
                    AuditLog.action == "EDIT",
                )
                .all()
            )
        self.assertTrue(entries)
        diff = json.loads(entries[-1].diff_json)
        self.assertEqual(diff["old"]["priority"], "MEDIUM")
        self.assertEqual(diff["new"]["priority"], "EMERGENCY")

    def test_existing_normal_ticket_flow_still_uses_medium_default(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        res = self.client.post("/api/tickets", json=self.ticket_payload())
        self.assertEqual(res.status_code, 201)
        created = res.get_json()
        self.assertEqual(created["priority"], "MEDIUM")

        detail = self.client.get(f"/api/tickets/{created['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["priority"], "MEDIUM")
