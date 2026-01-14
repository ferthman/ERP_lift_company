import unittest

from liftcrm import config, create_app
from liftcrm.utils.rate_limit import clear_rate_limits


class LoginRateLimitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        clear_rate_limits()
        self.client = self.app.test_client()

    def attempt(self, username, password, ip):
        return self.client.post(
            "/api/login",
            json={"username": username, "password": password},
            environ_overrides={"REMOTE_ADDR": ip},
        )

    def test_rate_limit_blocks_after_ten_attempts(self):
        for _ in range(10):
            res = self.attempt(config.ADMIN_USERNAME, "wrong-password", "10.0.0.1")
            self.assertEqual(res.status_code, 400)

        blocked = self.attempt(config.ADMIN_USERNAME, "wrong-password", "10.0.0.1")
        self.assertEqual(blocked.status_code, 429)
        payload = blocked.get_json()
        self.assertEqual(payload["error"]["code"], "RATE_LIMITED")
        self.assertIn("Too many login attempts", payload["error"]["message"])

    def test_rate_limit_isolated_by_username_and_ip(self):
        for _ in range(10):
            res = self.attempt(config.ADMIN_USERNAME, "wrong-password", "10.0.0.2")
            self.assertEqual(res.status_code, 400)

        blocked = self.attempt(config.ADMIN_USERNAME, "wrong-password", "10.0.0.2")
        self.assertEqual(blocked.status_code, 429)

        other_user = self.attempt(config.DISPATCHER_USERNAME, "wrong-password", "10.0.0.2")
        self.assertEqual(other_user.status_code, 400)

        other_ip = self.attempt(config.ADMIN_USERNAME, "wrong-password", "10.0.0.3")
        self.assertEqual(other_ip.status_code, 400)
