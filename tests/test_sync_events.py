import unittest
import uuid
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from liftcrm import create_app
from liftcrm.db import SessionLocal, Ticket, Master, User
from liftcrm.utils.rate_limit import clear_rate_limits
from liftcrm.utils.roles import ROLE_TECHNICIAN


class SyncEventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        clear_rate_limits()
        self.client = self.app.test_client()
        self.tech_password = "test-tech-pass"
        self.other_password = "other-tech-pass"
        self.tech_username = f"tech_{uuid.uuid4().hex[:8]}"
        self.other_username = f"tech_{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            master = Master(name=f"Тестовый мастер {self.tech_username}", is_active=1)
            other_master = Master(name=f"Тестовый мастер {self.other_username}", is_active=1)
            db.add_all([master, other_master])
            db.commit()
            db.refresh(master)
            db.refresh(other_master)
            tech_user = User(
                username=self.tech_username,
                password_hash=generate_password_hash(self.tech_password),
                role=ROLE_TECHNICIAN,
                master_id=master.id,
                is_active=1,
            )
            other_user = User(
                username=self.other_username,
                password_hash=generate_password_hash(self.other_password),
                role=ROLE_TECHNICIAN,
                master_id=other_master.id,
                is_active=1,
            )
            db.add_all([tech_user, other_user])
            db.commit()
            self.master_id = master.id
            self.other_master_id = other_master.id

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)

    def logout(self):
        self.client.post("/api/logout")

    def create_ticket(self, master_id, lat=43.238949, lon=76.889709, asset_id=None):
        with SessionLocal() as db:
            ticket = Ticket(
                object_name="Sync ticket",
                address="Test address",
                lat=lat,
                lon=lon,
                status="ASSIGNED",
                assigned_master_id=master_id,
                assigned_at=datetime.now(timezone.utc),
                asset_id=asset_id,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            return ticket.id

    def test_forbidden_ticket_sync(self):
        ticket_id = self.create_ticket(self.master_id)
        self.login(self.other_username, self.other_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_ACCEPT",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["results"][0]["ok"])
        self.assertEqual(data["results"][0]["code"], "FORBIDDEN")
        self.logout()

    def test_idempotency_on_accept(self):
        ticket_id = self.create_ticket(self.master_id)
        event_id = str(uuid.uuid4())
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": event_id,
                    "type": "TICKET_ACCEPT",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"current_lat": 43.238949, "current_lng": 76.889709},
                }
            ]
        }
        first = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(second.status_code, 200)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "ACCEPTED")
            self.assertEqual(ticket.version, 2)
        self.logout()

    def test_conflict_on_version_mismatch(self):
        ticket_id = self.create_ticket(self.master_id)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            ticket.version = 3
            db.commit()
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_ACCEPT",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"current_lat": 43.238949, "current_lng": 76.889709},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        data = res.get_json()
        self.assertFalse(data["results"][0]["ok"])
        self.assertEqual(data["results"][0]["code"], "CONFLICT")
        self.logout()

    def test_accept_out_of_range_returns_error(self):
        ticket_id = self.create_ticket(self.master_id, lat=43.245472, lon=76.885244)
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_ACCEPT",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"current_lat": 43.3, "current_lng": 76.9},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        result = data["results"][0]
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "OUT_OF_RANGE")
        self.assertIn("distance_m", result)
        self.assertEqual(result["radius_m"], 500)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "ASSIGNED")
        self.logout()

    def test_accept_within_range_succeeds(self):
        ticket_id = self.create_ticket(self.master_id, lat=43.245472, lon=76.885244)
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_ACCEPT",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"current_lat": 43.2456, "current_lng": 76.8853},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        result = data["results"][0]
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "OK")
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "ACCEPTED")
            self.assertEqual(ticket.version, 2)
        self.logout()

    def test_accept_requires_tech_coords(self):
        ticket_id = self.create_ticket(self.master_id, lat=43.245472, lon=76.885244)
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_ACCEPT",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        result = data["results"][0]
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "NO_TECH_COORDS")
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "ASSIGNED")
        self.logout()

    def test_accept_requires_target_coords(self):
        ticket_id = self.create_ticket(self.master_id, lat=0.0, lon=0.0)
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_ACCEPT",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"current_lat": 43.2456, "current_lng": 76.8853},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        result = data["results"][0]
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "NO_TARGET_COORDS")
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "ASSIGNED")
        self.logout()

    def test_happy_path_transitions(self):
        ticket_id = self.create_ticket(self.master_id)
        self.login(self.tech_username, self.tech_password)

        def send_event(event_type, expected_version, payload=None):
            payload = payload or {}
            if event_type == "TICKET_ACCEPT" and not payload:
                payload = {"current_lat": 43.238949, "current_lng": 76.889709}
            body = {
                "events": [
                    {
                        "id": str(uuid.uuid4()),
                        "type": event_type,
                        "ticket_id": ticket_id,
                        "expected_version": expected_version,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "payload": payload,
                    }
                ]
            }
            res = self.client.post("/api/sync/events", json=body)
            self.assertEqual(res.status_code, 200)
            return res.get_json()["results"][0]

        res = send_event("TICKET_ACCEPT", 1)
        self.assertTrue(res["ok"])
        res = send_event("TICKET_IN_PROGRESS", 2)
        self.assertTrue(res["ok"])
        res = send_event("TICKET_WAITING", 3, {"waiting_reason": "Нет доступа"})
        self.assertTrue(res["ok"])
        res = send_event("TICKET_IN_PROGRESS", 4)
        self.assertTrue(res["ok"])
        res = send_event("TICKET_DONE", 5, {"close_reason": "OTHER", "close_comment": "Работа завершена"})
        self.assertTrue(res["ok"])

        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "COMPLETED")
            self.assertEqual(ticket.version, 6)
        self.logout()

    def test_resume_from_waiting_preserves_arrived_at(self):
        ticket_id = self.create_ticket(self.master_id)
        original_arrived = datetime(2024, 5, 1, 8, 0)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            ticket.status = "WAITING"
            ticket.arrived_at = original_arrived
            ticket.arrival_lat = 43.238949
            ticket.arrival_lon = 76.889709
            ticket.waiting_reason = "Нет доступа"
            ticket.waiting_at = datetime(2024, 5, 1, 9, 0)
            db.commit()
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_IN_PROGRESS",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"lat": 44.0, "lon": 77.0},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(res.status_code, 200)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "IN_PROGRESS")
            self.assertEqual(ticket.arrived_at, original_arrived)
            self.assertEqual(ticket.arrival_lat, 43.238949)
            self.assertEqual(ticket.arrival_lon, 76.889709)
        self.logout()

    def test_in_progress_sets_arrived_at_once(self):
        ticket_id = self.create_ticket(self.master_id)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            ticket.status = "ACCEPTED"
            ticket.accepted_at = datetime.now(timezone.utc)
            ticket.arrived_at = None
            ticket.arrival_lat = None
            ticket.arrival_lon = None
            db.commit()
        self.login(self.tech_username, self.tech_password)
        payload = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "TICKET_IN_PROGRESS",
                    "ticket_id": ticket_id,
                    "expected_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"lat": 43.5, "lon": 76.5},
                }
            ]
        }
        res = self.client.post("/api/sync/events", json=payload)
        self.assertEqual(res.status_code, 200)
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.status, "IN_PROGRESS")
            self.assertIsNotNone(ticket.arrived_at)
            self.assertEqual(ticket.arrival_lat, 43.5)
            self.assertEqual(ticket.arrival_lon, 76.5)
        self.logout()
