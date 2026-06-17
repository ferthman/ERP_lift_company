import importlib
import os
import sqlite3
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from liftcrm import config, create_app


class DatabaseInitTest(unittest.TestCase):
    def setUp(self):
        self.original_db_path = config.DB_PATH
        self.original_archive_path = config.ARCHIVE_PATH
        self.original_upload_folder = config.UPLOAD_FOLDER

    def tearDown(self):
        config.DB_PATH = self.original_db_path
        config.ARCHIVE_PATH = self.original_archive_path
        config.UPLOAD_FOLDER = self.original_upload_folder
        import liftcrm.db as db_module
        import liftcrm.tickets.service as service_module

        importlib.reload(db_module)
        importlib.reload(service_module)

    def test_fresh_db_initializes_without_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "fresh.db")
            config.DB_PATH = db_path
            config.ARCHIVE_PATH = os.path.join(tmpdir, "archive.xlsx")
            config.UPLOAD_FOLDER = os.path.join(tmpdir, "uploads")

            import liftcrm.db as db_module
            import liftcrm.tickets.service as service_module

            importlib.reload(db_module)
            importlib.reload(service_module)

            app = create_app()
            app.config["TESTING"] = True
            client = app.test_client()
            res = client.get("/")
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers.get("Location"), "/login?next=/")

    def test_auto_assign_requires_linked_technician(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "assign.db")
            config.DB_PATH = db_path
            config.ARCHIVE_PATH = os.path.join(tmpdir, "archive.xlsx")
            config.UPLOAD_FOLDER = os.path.join(tmpdir, "uploads")

            import liftcrm.db as db_module
            import liftcrm.tickets.service as service_module

            importlib.reload(db_module)
            importlib.reload(service_module)

            db_module.init_db()
            with db_module.SessionLocal() as db:
                for user in db.query(db_module.User).filter(db_module.User.master_id.isnot(None)).all():
                    user.is_active = 0
                db.commit()

                master = db_module.Master(name="Без доступа", is_active=1)
                db.add(master)
                db.commit()
                db.refresh(master)

                selected = service_module.auto_assign_master(db)
                self.assertIsNone(selected)

                user = db_module.User(
                    username="tech_access",
                    password_hash=generate_password_hash("secret"),
                    role="technician",
                    master_id=master.id,
                    is_active=1,
                )
                db.add(user)
                db.commit()

                selected = service_module.auto_assign_master(db)
                self.assertIsNotNone(selected)
                self.assertEqual(selected.id, master.id)

    def test_migration_adds_ticket_problem_type_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "legacy-problem-type.db")
            config.DB_PATH = db_path
            config.ARCHIVE_PATH = os.path.join(tmpdir, "archive.xlsx")
            config.UPLOAD_FOLDER = os.path.join(tmpdir, "uploads")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE masters (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
            cur.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, master_id INTEGER)"
            )
            cur.execute(
                """
                CREATE TABLE tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_name TEXT NOT NULL,
                    address TEXT,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    description TEXT,
                    status TEXT,
                    assigned_master_id INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
            conn.commit()
            conn.close()

            import liftcrm.db as db_module

            importlib.reload(db_module)
            db_module.ensure_migrations()

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(tickets)")
            columns = {row[1] for row in cur.fetchall()}
            cur.execute("PRAGMA index_list(tickets)")
            indexes = {row[1] for row in cur.fetchall()}
            conn.close()

            self.assertIn("problem_type", columns)
            self.assertIn("idx_tickets_problem_type", indexes)
