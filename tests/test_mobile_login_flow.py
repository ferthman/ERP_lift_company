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
            admin_user = db.query(User).filter_by(username="admin_login_test").first()
            if admin_user is None:
                admin_user = User(
                    username="admin_login_test",
                    password_hash=generate_password_hash("adminpass"),
                    role="admin",
                    is_active=1,
                )
                db.add(admin_user)
            db.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def login_api(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def test_login_page_renders_unified_ui(self):
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Вход", body)
        self.assertIn("Если у вас нет доступа, обратитесь к администратору.", body)

    def test_mobile_unauthenticated_redirects_to_login(self):
        res = self.client.get("/mobile")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/login?next=/mobile")

    def test_admin_unauthenticated_redirects_to_login(self):
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/login?next=/admin")

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

    def test_technician_admin_preference_allows_root(self):
        self.login_api("tech_mobile_test", "techpass")
        admin_res = self.client.get("/admin?ui=admin")
        self.assertEqual(admin_res.status_code, 200)

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Lift CRM", body)

    def test_admin_route_not_redirected(self):
        self.login_api("tech_mobile_test", "techpass")
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Lift CRM", body)
        self.assertIn("Вы вошли как мастер. В админке доступ ограничен.", body)
        self.assertIn("Если вам нужна админка — войдите под диспетчером/админом.", body)
        self.assertIn("/mobile?ui=mobile", body)
        self.assertIn(">Выйти<", body)

    def test_non_technician_mobile_notice(self):
        self.login_api("dispatcher_mobile_test", "disppass")
        res = self.client.get("/mobile")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Это приложение для мастеров", body)
        self.assertIn("Перейти в админку", body)

    def test_non_technician_root_unchanged(self):
        self.login_api("dispatcher_mobile_test", "disppass")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Lift CRM", body)
        self.assertNotIn("Вы вошли как мастер. В админке доступ ограничен.", body)
        self.assertNotIn("Если вам нужна админка — войдите под диспетчером/админом.", body)

    def test_logout_action_clears_session(self):
        self.login_api("tech_mobile_test", "techpass")
        logout_res = self.client.get("/logout")
        self.assertEqual(logout_res.status_code, 302)
        self.assertEqual(logout_res.headers.get("Location"), "/login")
        res = self.client.get("/api/me")
        payload = res.get_json()
        self.assertFalse(payload["authenticated"])
        admin_res = self.client.get("/admin")
        self.assertEqual(admin_res.status_code, 302)
        self.assertEqual(admin_res.headers.get("Location"), "/login?next=/admin")
        mobile_res = self.client.get("/mobile")
        self.assertEqual(mobile_res.status_code, 302)
        self.assertEqual(mobile_res.headers.get("Location"), "/login?next=/mobile")

    def test_desktop_template_uses_logout_route(self):
        self.login_api("dispatcher_mobile_test", "disppass")
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("/logout", body)
        self.assertNotIn("/api/logout", body)

    def test_login_technician_redirects_to_mobile(self):
        res = self.client.post(
            "/login",
            data={"username": "tech_mobile_test", "password": "techpass", "next": "/admin"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/mobile")

        res = self.client.post(
            "/login",
            data={"username": "tech_mobile_test", "password": "techpass", "next": "/mobile?ui=mobile"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/mobile?ui=mobile")

    def test_login_admin_redirects_to_admin(self):
        res = self.client.post(
            "/login",
            data={"username": "admin_login_test", "password": "adminpass", "next": "/admin"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/admin")

        res = self.client.post(
            "/login",
            data={"username": "admin_login_test", "password": "adminpass", "next": "/mobile"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/admin")

        res = self.client.post(
            "/login",
            data={"username": "admin_login_test", "password": "adminpass", "next": "/mobile?foo=bar"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/admin")

        res = self.client.post(
            "/login",
            data={
                "username": "admin_login_test",
                "password": "adminpass",
                "next": "/%2F%2Fevil.com",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        res = self.client.post(
            "/login",
            data={"username": "admin_login_test", "password": "adminpass", "next": "/\\evil.com"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        res = self.client.post(
            "/login",
            data={"username": "admin_login_test", "password": "adminpass", "next": "//evil.com"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        res = self.client.post(
            "/login",
            data={"username": "admin_login_test", "password": "adminpass", "next": "https://evil.com"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        res = self.client.post(
            "/login",
            data={"username": "admin_login_test", "password": "adminpass", "next": " /mobile "},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/admin")
