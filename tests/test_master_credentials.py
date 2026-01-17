import unittest

from werkzeug.security import check_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Master, User
from liftcrm.utils.users import ROLE_TECHNICIAN


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

    def create_master_user(self, master_id, payload=None):
        res = self.client.post(f"/api/masters/{master_id}/create-user", json=payload or {})
        return res

    def test_create_master_user_creates_credentials(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        first = self.create_master("Тестовый мастер A")
        res = self.create_master_user(first["id"])
        self.assertEqual(res.status_code, 201)
        payload = res.get_json()
        self.assertTrue(payload["temp_password"])

        with SessionLocal() as db:
            master = db.get(Master, first["id"])
            user = db.query(User).filter(User.master_id == master.id, User.role == ROLE_TECHNICIAN).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, payload["username"])
            self.assertTrue(check_password_hash(user.password_hash, payload["temp_password"]))

    def test_create_master_user_conflict(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер B")
        first = self.create_master_user(created["id"])
        self.assertEqual(first.status_code, 201)
        second = self.create_master_user(created["id"])
        self.assertEqual(second.status_code, 409)

    def test_reset_password_updates_user(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер C")
        res = self.create_master_user(created["id"])
        self.assertEqual(res.status_code, 201)
        user_payload = res.get_json()

        res = self.client.post(f"/api/users/{user_payload['user_id']}/reset-password")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["username"])
        self.assertTrue(data["temp_password"])

        with SessionLocal() as db:
            user = db.query(User).filter(User.master_id == created["id"], User.role == ROLE_TECHNICIAN).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, data["username"])
            self.assertTrue(check_password_hash(user.password_hash, data["temp_password"]))

    def test_reset_password_forbidden_for_non_admin(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер D")
        res = self.create_master_user(created["id"])
        self.assertEqual(res.status_code, 201)
        user_payload = res.get_json()
        self.logout()

        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        res = self.client.post(f"/api/users/{user_payload['user_id']}/reset-password")
        self.assertEqual(res.status_code, 403)

    def test_role_master_validation(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер E")
        res = self.client.post("/api/users", json={"username": "bad-dispatch", "role": "dispatcher", "master_id": created["id"]})
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/users", json={"username": "bad-tech", "role": "technician"})
        self.assertEqual(res.status_code, 400)

    def test_unique_master_link(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        created = self.create_master("Тестовый мастер F")
        res = self.create_master_user(created["id"])
        self.assertEqual(res.status_code, 201)
        res = self.client.post(
            "/api/users",
            json={"username": "second-tech", "role": "technician", "master_id": created["id"]},
        )
        self.assertEqual(res.status_code, 409)
