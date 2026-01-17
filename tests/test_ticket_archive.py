import unittest
import uuid

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket, User, Master
from liftcrm.utils.roles import ROLE_TECHNICIAN


class TicketArchiveApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
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
            db.commit()

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def logout(self):
        self.client.post("/api/logout")

    def create_ticket(self):
        payload = {
            "object_name": "Archive Test Object",
            "lat": 43.238949,
            "lon": 76.889709,
            "description": "Archive test ticket",
        }
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def test_archive_idempotent_delete_disabled_and_master_forbidden(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        ticket_id_for_master = self.create_ticket()

        first = self.client.post(f"/api/tickets/{ticket_id}/archive")
        self.assertEqual(first.status_code, 200)
        first_data = first.get_json()
        self.assertTrue(first_data["archived_at"])
        first_archived = first_data["archived_at"]

        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertIsNotNone(ticket.archived_at)
            stored_first = ticket.archived_at

        second = self.client.post(f"/api/tickets/{ticket_id}/archive")
        self.assertEqual(second.status_code, 200)
        second_data = second.get_json()
        self.assertEqual(second_data["archived_at"], first_archived)

        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.archived_at, stored_first)

        delete_res = self.client.delete(f"/api/tickets/{ticket_id}")
        self.assertEqual(delete_res.status_code, 405)

        self.logout()

        self.login(self.tech_username, self.master_password)
        forbidden = self.client.post(f"/api/tickets/{ticket_id_for_master}/archive")
        self.assertIn(forbidden.status_code, (401, 403))
