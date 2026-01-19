import unittest

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Master, User, init_db


class MobileLoginFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app
        init_db()
        with SessionLocal() as db:
            master = (
                db.query(Master)
                .outerjoin(User)
                .filter(User.id.is_(None))
                .order_by(Master.id)
                .first()
            )
            if master is None:
                master = Master(name="Мастер тест")
                db.add(master)
                db.commit()
                db.refresh(master)
            tech_user = db.query(User).filter_by(username="tech_mobile_test").first()
            if tech_user is None:
                tech_user = User(
                    username="tech_mobile_test",
                    password_hash=generate_password_hash("techpass"),
                    role="technician",
                    master_id=master.id,
                    is_active=1,
                )
                db.add(tech_user)
            dispatcher_user = db.query(User).filter_by(username="dispatcher_mobile_test").first()
            if dispatcher_user is None:
                dispatcher_user = User(
                    username="dispatcher_mobile_test",
                    password_hash=generate_password_hash("disppass"),
                    role="dispatcher",
                    is_active=1,
                )
                db.add(dispatcher_user)
            db.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def login_api(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def test_mobile_unauthenticated_shows_login(self):
        res = self.client.get("/mobile")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Вход для мастеров", body)
        self.assertIn("name=\"username\"", body)

    def test_technician_redirects_from_root_and_sees_mobile(self):
        self.login_api("tech_mobile_test", "techpass")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/mobile", res.headers.get("Location", ""))

        mobile_res = self.client.get("/mobile")
        self.assertEqual(mobile_res.status_code, 200)
        body = mobile_res.get_data(as_text=True)
        self.assertIn("Приложение мастера", body)
        self.assertIn("Мои заявки", body)

    def test_non_technician_mobile_notice(self):
        self.login_api("dispatcher_mobile_test", "disppass")
        res = self.client.get("/mobile")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Это приложение для мастеров", body)
        self.assertIn("Перейти в админку", body)

    def test_login_next_redirect_is_safe(self):
        res = self.client.post(
            "/login",
            data={"username": "tech_mobile_test", "password": "techpass", "next": "/mobile"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/mobile")

        res = self.client.post(
            "/login",
            data={
                "username": "tech_mobile_test",
                "password": "techpass",
                "next": "https://evil.com",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        res = self.client.post(
            "/login",
            data={"username": "tech_mobile_test", "password": "techpass", "next": "//evil.com"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")
