import unittest
import uuid

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Master, Ticket, User, ensure_migrations
from liftcrm.utils.roles import ROLE_TECHNICIAN


class MobileTicketCoordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        ensure_migrations()
        self.client = self.app.test_client()
        self.master_password = "test-tech-pass"
        self.tech_username = f"tech_{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            master = Master(name=f"Тестовый мастер {self.tech_username}", is_active=1)
            db.add(master)
            db.commit()
            db.refresh(master)
            user = User(
                username=self.tech_username,
                password_hash=generate_password_hash(self.master_password),
                role=ROLE_TECHNICIAN,
                master_id=master.id,
                is_active=1,
            )
            db.add(user)
            ticket = Ticket(
                object_name="Тестовый объект",
                address="Алматы, ул. Толе Би 1",
                lat=43.238949,
                lon=76.889709,
                status="ASSIGNED",
                assigned_master_id=master.id,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            self.ticket_id = ticket.id

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def test_mobile_endpoints_include_lat_lng(self):
        self.login(self.tech_username, self.master_password)
        list_res = self.client.get("/api/me/tickets")
        self.assertEqual(list_res.status_code, 200)
        tickets = list_res.get_json()
        self.assertTrue(any(t["id"] == self.ticket_id for t in tickets))
        target = next(t for t in tickets if t["id"] == self.ticket_id)
        self.assertEqual(target["lat"], 43.238949)
        self.assertEqual(target["lng"], 76.889709)

        detail_res = self.client.get(f"/api/tickets/{self.ticket_id}")
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.get_json()
        self.assertEqual(detail["lat"], 43.238949)
        self.assertEqual(detail["lng"], 76.889709)
