import unittest

from werkzeug.security import check_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Master, User
from liftcrm.utils.roles import ROLE_TECHNICIAN


class MasterCredentialsTest(unittest.TestCase):
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

    def test_assign_role_generates_unique_password(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        first = self.create_master("Тестовый мастер A")
        second = self.create_master("Тестовый мастер B")
        first_access = self.assign_role(first["id"])
        second_access = self.assign_role(second["id"])
        self.assertNotEqual(first_access["temp_password"], second_access["temp_password"])

        with SessionLocal() as db:
            master = db.get(Master, first["id"])
            user = db.query(User).filter(User.master_id == master.id).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, first_access["username"])
            self.assertEqual(user.role, ROLE_TECHNICIAN)
            self.assertTrue(check_password_hash(user.password_hash, first_access["temp_password"]))

            second_user = db.query(User).filter(User.master_id == second["id"]).first()
            self.assertIsNotNone(second_user)
            self.assertNotEqual(user.password_hash, second_user.password_hash)

    def test_reset_password_creates_missing_user(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер C")
        access = self.assign_role(created["id"])

        with SessionLocal() as db:
            user = db.query(User).filter(User.master_id == created["id"]).first()
            self.assertIsNotNone(user)
            db.delete(user)
            db.commit()

        res = self.client.post(f"/api/masters/{created['id']}/assign-role", json={"role": "TECHNICIAN"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["username"])
        self.assertTrue(data["temp_password"])

        with SessionLocal() as db:
            user = db.query(User).filter(User.master_id == created["id"]).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, data["username"])
            self.assertTrue(check_password_hash(user.password_hash, data["temp_password"]))

    def test_reset_password_forbidden_for_non_admin(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер D")
        access = self.assign_role(created["id"])
        self.logout()

        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        res = self.client.post(f"/api/users/{access['user_id']}/reset-password")
        self.assertEqual(res.status_code, 403)
