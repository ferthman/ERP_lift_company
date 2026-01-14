import unittest

from werkzeug.security import check_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Master, User


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

    def test_create_master_generates_unique_password(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        first = self.create_master("Тестовый мастер A")
        second = self.create_master("Тестовый мастер B")
        self.assertNotEqual(first["temp_password"], second["temp_password"])

        with SessionLocal() as db:
            master = db.get(Master, first["id"])
            user = db.query(User).filter(User.master_id == master.id, User.role == "master").first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, first["username"])
            self.assertTrue(check_password_hash(user.password_hash, first["temp_password"]))

            second_user = db.query(User).filter(User.master_id == second["id"], User.role == "master").first()
            self.assertIsNotNone(second_user)
            self.assertNotEqual(user.password_hash, second_user.password_hash)

    def test_reset_password_creates_missing_user(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер C")

        with SessionLocal() as db:
            user = db.query(User).filter(User.master_id == created["id"], User.role == "master").first()
            self.assertIsNotNone(user)
            db.delete(user)
            db.commit()

        res = self.client.post(f"/api/masters/{created['id']}/reset_password")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["username"])
        self.assertTrue(data["temp_password"])

        with SessionLocal() as db:
            user = db.query(User).filter(User.master_id == created["id"], User.role == "master").first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, data["username"])
            self.assertTrue(check_password_hash(user.password_hash, data["temp_password"]))

    def test_reset_password_forbidden_for_non_admin(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер D")
        self.logout()

        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        res = self.client.post(f"/api/masters/{created['id']}/reset_password")
        self.assertEqual(res.status_code, 403)
