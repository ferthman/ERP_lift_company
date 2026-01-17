import unittest

from werkzeug.security import generate_password_hash

from liftcrm import create_app
from liftcrm.db import SessionLocal, Master, Ticket, User
from liftcrm.utils.users import ROLE_TECHNICIAN


class TechnicianIsolationTest(unittest.TestCase):
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

    def _create_master(self, name):
        with SessionLocal() as db:
            master = Master(name=name, is_active=1)
            db.add(master)
            db.commit()
            db.refresh(master)
            return master

    def _create_user(self, username, password, role, master_id=None):
        with SessionLocal() as db:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                role=role,
                master_id=master_id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user

    def _create_ticket(self, master_id, object_name):
        with SessionLocal() as db:
            ticket = Ticket(
                object_name=object_name,
                lat=43.238949,
                lon=76.889709,
                status="ASSIGNED",
                assigned_master_id=master_id,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            return ticket

    def test_technician_sees_only_own_tickets(self):
        master_one = self._create_master("Мастер A")
        master_two = self._create_master("Мастер B")
        user_one = self._create_user("tech-one", "pass-one", ROLE_TECHNICIAN, master_one.id)
        self._create_user("tech-two", "pass-two", ROLE_TECHNICIAN, master_two.id)
        ticket_one = self._create_ticket(master_one.id, "Ticket A")
        ticket_two = self._create_ticket(master_two.id, "Ticket B")

        self.login(user_one.username, "pass-one")
        res = self.client.get("/api/tickets")
        self.assertEqual(res.status_code, 200)
        ids = {t["id"] for t in res.get_json()}
        self.assertIn(ticket_one.id, ids)
        self.assertNotIn(ticket_two.id, ids)

        res = self.client.get(f"/api/tickets/{ticket_two.id}")
        self.assertEqual(res.status_code, 403)

    def test_technician_without_master_id_blocked(self):
        user = self._create_user("tech-orphan", "pass-orphan", ROLE_TECHNICIAN, None)
        self.login(user.username, "pass-orphan")
        res = self.client.get("/api/tickets")
        self.assertEqual(res.status_code, 403)
