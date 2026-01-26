import re
import unittest

from werkzeug.security import generate_password_hash

from liftcrm import create_app
from liftcrm.db import SessionLocal, Master, User, init_db


class DesktopNavRbacTest(unittest.TestCase):
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
            if db.query(User).filter_by(username="admin_nav_test").first() is None:
                db.add(
                    User(
                        username="admin_nav_test",
                        password_hash=generate_password_hash("adminpass"),
                        role="admin",
                        is_active=1,
                    )
                )
            if db.query(User).filter_by(username="dispatcher_nav_test").first() is None:
                db.add(
                    User(
                        username="dispatcher_nav_test",
                        password_hash=generate_password_hash("disppass"),
                        role="dispatcher",
                        is_active=1,
                    )
                )
            if db.query(User).filter_by(username="tech_nav_test").first() is None:
                db.add(
                    User(
                        username="tech_nav_test",
                        password_hash=generate_password_hash("techpass"),
                        role="technician",
                        master_id=master.id,
                        is_active=1,
                    )
                )
            db.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def login_api(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def test_admin_nav_items(self):
        self.login_api("admin_nav_test", "adminpass")
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        for label in [
            "Панель",
            "Контроль этапов",
            "Лифты",
            "Объекты",
            "Админ",
            "Пользователи и допуск",
        ]:
            self.assertIn(label, body)
        self.assertNotIn("Приложение мастера", body)

    def test_dispatcher_nav_items(self):
        self.login_api("dispatcher_nav_test", "disppass")
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        for label in ["Панель", "Контроль этапов", "Лифты", "Объекты"]:
            self.assertIn(label, body)
        self.assertNotIn("Админ", body)
        self.assertNotIn("Пользователи и допуск", body)
        self.assertNotIn("Приложение мастера", body)

    def test_admin_status_labels_localized(self):
        self.login_api("admin_nav_test", "adminpass")
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.S)
        body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", body)
        text = re.sub(r"\s+", " ", text)
        self.assertIn("Новая", text)
        self.assertIn("В работе", text)
        self.assertNotIn("IN_PROGRESS", text)

    def test_technician_admin_banner_only(self):
        self.login_api("tech_nav_test", "techpass")
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        for label in ["Панель", "Контроль этапов", "Лифты", "Объекты", "Админ", "Пользователи и допуск"]:
            self.assertNotIn(label, body)
        self.assertNotIn("const API = location.origin", body)
        self.assertIn("Вернуться в приложение мастера", body)
        self.assertIn("/mobile", body)
        self.assertIn("/logout", body)
