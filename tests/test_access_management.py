import unittest

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Master, User, Ticket
from liftcrm.utils.roles import ROLE_TECHNICIAN


class AccessManagementTest(unittest.TestCase):
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

    def logout(self):
        self.client.post("/api/logout")

    def create_master(self, name):
        res = self.client.post("/api/masters", json={"name": name})
        self.assertEqual(res.status_code, 201)
        return res.get_json()

    def assign_role(self, master_id, username=None):
        payload = {"role": "TECHNICIAN"}
        if username:
            payload["username"] = username
        res = self.client.post(f"/api/masters/{master_id}/assign-role", json=payload)
        self.assertEqual(res.status_code, 200)
        return res.get_json()

    def test_unique_master_link(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        first = self.create_master("Мастер A")
        second = self.create_master("Мастер B")
        first_user = self.assign_role(first["id"])
        second_user = self.assign_role(second["id"])

        res = self.client.patch(
            f"/api/users/{second_user['user_id']}",
            json={"role": "TECHNICIAN", "master_id": first["id"]},
        )
        self.assertEqual(res.status_code, 409)

    def test_role_master_id_rules(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        master = self.create_master("Мастер Роли")
        access = self.assign_role(master["id"])

        res = self.client.patch(
            f"/api/users/{access['user_id']}",
            json={"role": "DISPATCHER", "master_id": master["id"]},
        )
        self.assertEqual(res.status_code, 400)

        res = self.client.patch(
            f"/api/users/{access['user_id']}",
            json={"role": "TECHNICIAN", "master_id": None},
        )
        self.assertEqual(res.status_code, 400)

    def test_replace_technician_flow(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        old_master = self.create_master("Мастер Старый")
        new_master = self.create_master("Мастер Новый")
        access = self.assign_role(old_master["id"])

        with SessionLocal() as db:
            ticket = Ticket(
                object_name="Заявка 1",
                lat=43.0,
                lon=76.0,
                status="NEW",
                priority="MEDIUM",
                assigned_master_id=old_master["id"],
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)

        res = self.client.post(
            "/api/access/replace-technician",
            json={
                "old_master_id": old_master["id"],
                "new_master_id": new_master["id"],
                "reassign_open_tickets": True,
                "disable_old_user": True,
                "deactivate_old_master": False,
            },
        )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["reassigned_tickets"], 1)

        with SessionLocal() as db:
            updated = db.get(Ticket, ticket.id)
            self.assertEqual(updated.assigned_master_id, new_master["id"])
            user = db.query(User).filter(User.master_id == old_master["id"]).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.is_active, 0)

    def test_technician_isolation(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        master_a = self.create_master("Мастер A2")
        master_b = self.create_master("Мастер B2")
        access_a = self.assign_role(master_a["id"], username="tech_a")
        access_b = self.assign_role(master_b["id"], username="tech_b")
        with SessionLocal() as db:
            t1 = Ticket(
                object_name="Заявка A",
                lat=43.1,
                lon=76.1,
                status="ASSIGNED",
                priority="MEDIUM",
                assigned_master_id=master_a["id"],
            )
            t2 = Ticket(
                object_name="Заявка B",
                lat=43.2,
                lon=76.2,
                status="ASSIGNED",
                priority="MEDIUM",
                assigned_master_id=master_b["id"],
            )
            db.add_all([t1, t2])
            db.commit()

        self.logout()
        self.login(access_a["username"], access_a["temp_password"])
        res = self.client.get("/api/tickets")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(all(str(item["assigned_master_id"]) == str(master_a["id"]) for item in data))

        with SessionLocal() as db:
            rogue = User(
                username="tech_missing",
                password_hash=generate_password_hash("secret"),
                role=ROLE_TECHNICIAN,
                master_id=None,
                is_active=1,
            )
            db.add(rogue)
            db.commit()

        self.logout()
        self.login("tech_missing", "secret")
        res = self.client.get("/api/tickets")
        self.assertEqual(res.status_code, 403)
