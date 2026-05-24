import importlib
import os
import tempfile
import unittest

from liftcrm import config


class SeedDemoCleanupTest(unittest.TestCase):
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

    def test_fresh_seed_creates_staff_baseline_without_operational_demo_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config.DB_PATH = os.path.join(tmpdir, "fresh.db")
            config.ARCHIVE_PATH = os.path.join(tmpdir, "archive.xlsx")
            config.UPLOAD_FOLDER = os.path.join(tmpdir, "uploads")

            import liftcrm.db as db_module
            import liftcrm.tickets.service as service_module

            importlib.reload(db_module)
            importlib.reload(service_module)
            db_module.init_db()
            db_module.ensure_migrations()

            with db_module.SessionLocal() as db:
                users = db.query(db_module.User).order_by(db_module.User.username).all()
                masters = db.query(db_module.Master).order_by(db_module.Master.id).all()

                self.assertEqual(db.query(db_module.Ticket).count(), 0)
                self.assertEqual(db.query(db_module.Asset).count(), 0)
                self.assertEqual(len(masters), 5)
                self.assertTrue(all(master.is_active for master in masters))
                self.assertEqual(len(users), 7)
                self.assertEqual(
                    {user.username for user in users},
                    {"admin", "dispatcher", "master1", "master2", "master3", "master4", "master5"},
                )
                self.assertEqual(
                    {user.role for user in users if user.username.startswith("master")},
                    {"technician"},
                )
                self.assertTrue(all(user.master_id for user in users if user.username.startswith("master")))

