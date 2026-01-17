import importlib
import os
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
            self.assertEqual(res.status_code, 200)

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
