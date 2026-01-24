import unittest
import uuid

from liftcrm import create_app, config


class ChangePasswordTest(unittest.TestCase):
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

    def test_admin_can_change_password_and_login(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        master = self.create_master("Техник пароль")
        access = self.assign_role(master["id"], username=f"tech_{uuid.uuid4().hex[:6]}")

        new_password = "new-strong-password"
        res = self.client.post(
            f"/api/users/{access['user_id']}/password",
            json={"password": new_password},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

        self.logout()
        res = self.client.post("/api/login", json={"username": access["username"], "password": new_password})
        self.assertEqual(res.status_code, 200)

    def test_non_admin_cannot_change_password(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        master = self.create_master("Техник запрет")
        access = self.assign_role(master["id"], username=f"tech_{uuid.uuid4().hex[:6]}")
        self.logout()

        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        res = self.client.post(
            f"/api/users/{access['user_id']}/password",
            json={"password": "forbidden-pass"},
        )
        self.assertEqual(res.status_code, 403)

    def test_password_validation_too_short(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        master = self.create_master("Техник короткий")
        access = self.assign_role(master["id"], username=f"tech_{uuid.uuid4().hex[:6]}")

        res = self.client.post(
            f"/api/users/{access['user_id']}/password",
            json={"password": "short"},
        )
        self.assertEqual(res.status_code, 400)
        payload = res.get_json()
        error = payload.get("error", "")
        if isinstance(error, dict):
            error = error.get("message", "")
        self.assertIn("Пароль должен быть", error)
