import unittest

from liftcrm import config, create_app
from liftcrm.utils.rate_limit import clear_rate_limits


class LoginRateLimitTest(unittest.TestCase):
    def setUp(self):
        clear_rate_limits()
        self._orig_trust_proxy = config.TRUST_PROXY_HEADERS
        self._orig_proxy_x_for = config.PROXY_FIX_X_FOR
        config.TRUST_PROXY_HEADERS = False
        config.PROXY_FIX_X_FOR = 1
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        config.TRUST_PROXY_HEADERS = self._orig_trust_proxy
        config.PROXY_FIX_X_FOR = self._orig_proxy_x_for

    def attempt(self, username, password, ip, headers=None):
        return self.client.post(
            "/api/login",
            json={"username": username, "password": password},
            environ_overrides={"REMOTE_ADDR": ip},
            headers=headers or {},
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

    def test_proxy_headers_ignored_by_default(self):
        for _ in range(10):
            res = self.attempt(
                config.ADMIN_USERNAME,
                "wrong-password",
                "10.0.0.10",
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            self.assertEqual(res.status_code, 400)

        other_ip = self.attempt(
            config.ADMIN_USERNAME,
            "wrong-password",
            "10.0.0.11",
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        self.assertEqual(other_ip.status_code, 400)

    def test_proxy_headers_used_when_enabled(self):
        clear_rate_limits()
        config.TRUST_PROXY_HEADERS = True
        config.PROXY_FIX_X_FOR = 1
        proxy_app = create_app()
        proxy_app.config["TESTING"] = True
        proxy_client = proxy_app.test_client()

        for _ in range(10):
            res = proxy_client.post(
                "/api/login",
                json={"username": config.ADMIN_USERNAME, "password": "wrong-password"},
                environ_overrides={"REMOTE_ADDR": "10.0.0.20"},
                headers={"X-Forwarded-For": "198.51.100.20"},
            )
            self.assertEqual(res.status_code, 400)

        blocked = proxy_client.post(
            "/api/login",
            json={"username": config.ADMIN_USERNAME, "password": "wrong-password"},
            environ_overrides={"REMOTE_ADDR": "10.0.0.21"},
            headers={"X-Forwarded-For": "198.51.100.20"},
        )
        self.assertEqual(blocked.status_code, 429)
