import importlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from liftcrm import config, create_app


class MetricsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        self.original_archive_path = config.ARCHIVE_PATH
        self.original_upload_folder = config.UPLOAD_FOLDER

        config.DB_PATH = os.path.join(self.tmpdir.name, "metrics.db")
        config.ARCHIVE_PATH = os.path.join(self.tmpdir.name, "archive.xlsx")
        config.UPLOAD_FOLDER = os.path.join(self.tmpdir.name, "uploads")

        self.db_module = self.reload_db_bound_modules()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

    def tearDown(self):
        self.db_module.SessionLocal.remove()
        config.DB_PATH = self.original_db_path
        config.ARCHIVE_PATH = self.original_archive_path
        config.UPLOAD_FOLDER = self.original_upload_folder
        self.reload_db_bound_modules()
        self.tmpdir.cleanup()

    def reload_db_bound_modules(self):
        import liftcrm.db as db_module
        import liftcrm.tickets.repository as repository_module
        import liftcrm.tickets.service as service_module
        import liftcrm.tickets.routes as routes_module

        db_module = importlib.reload(db_module)
        importlib.reload(repository_module)
        importlib.reload(service_module)
        importlib.reload(routes_module)
        return db_module

    def login(self, username, password):
        res = self.client.post(
            "/api/login",
            json={"username": username, "password": password},
            environ_overrides={"REMOTE_ADDR": "198.51.100.77"},
        )
        self.assertEqual(res.status_code, 200)
        return res

    def test_default_seeded_db_metrics_shape_is_valid(self):
        res = self.client.get("/api/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["total_tickets"], 0)
        self.assertEqual(data["overall"]["total"], 0)
        self.assertEqual(len(data["masters"]), 5)
        self.assertEqual(data["response_sla_breach_percent"], 0)
        self.assertEqual(data["completion_sla_breach_percent"], 0)
        self.assert_metrics_shape(data)

    def test_multiple_masters_are_returned(self):
        master_ids = self.seed_tickets_for_two_masters()

        res = self.client.get("/api/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        returned_ids = [master["id"] for master in data["masters"]]
        self.assertIn(master_ids[0], returned_ids)
        self.assertIn(master_ids[1], returned_ids)
        self.assertGreaterEqual(len(returned_ids), 2)

        by_id = {master["id"]: master for master in data["masters"]}
        self.assertEqual(by_id[master_ids[0]]["total"], 1)
        self.assertEqual(by_id[master_ids[0]]["counts"]["COMPLETED"], 1)
        self.assertEqual(by_id[master_ids[1]]["total"], 1)
        self.assertEqual(by_id[master_ids[1]]["counts"]["NEW"], 1)
        self.assertEqual(data["total_tickets"], 2)
        self.assert_metrics_shape(data)

    def test_zero_masters_returns_200_with_empty_masters(self):
        with self.db_module.SessionLocal() as db:
            db.query(self.db_module.Master).delete()
            db.commit()

        res = self.client.get("/api/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["masters"], [])
        self.assertEqual(data["total_tickets"], 0)
        self.assertEqual(data["overall"]["total"], 0)
        self.assert_metrics_shape(data)

    def seed_tickets_for_two_masters(self):
        with self.db_module.SessionLocal() as db:
            masters = db.query(self.db_module.Master).order_by(self.db_module.Master.id).limit(2).all()
            self.assertEqual(len(masters), 2)
            created = datetime.now(timezone.utc) - timedelta(hours=2)
            completed = created + timedelta(hours=1)
            first = self.db_module.Ticket(
                object_name="Metrics completed",
                address="A",
                lat=43.0,
                lon=76.0,
                description="Done",
                status="COMPLETED",
                priority="HIGH",
                assigned_master_id=masters[0].id,
                created_at=created,
                completed_at=completed,
                close_reason="OTHER",
            )
            second = self.db_module.Ticket(
                object_name="Metrics new",
                address="B",
                lat=43.1,
                lon=76.1,
                description="Open",
                status="NEW",
                priority="LOW",
                assigned_master_id=masters[1].id,
                created_at=created,
            )
            db.add_all([first, second])
            db.commit()
            return [masters[0].id, masters[1].id]

    def assert_metrics_shape(self, data):
        expected_top_level = {
            "overall",
            "masters",
            "total_tickets",
            "response_sla_breached_count",
            "completion_sla_breached_count",
            "response_sla_breach_percent",
            "completion_sla_breach_percent",
            "tickets_by_close_reason",
            "sla_breaches_by_reason",
            "tickets_by_priority",
        }
        self.assertTrue(expected_top_level.issubset(data.keys()))
        self.assertTrue({"total", "counts", "avg_close_sec", "median_close_sec"}.issubset(data["overall"].keys()))
        self.assertTrue(
            {
                "NEW",
                "ASSIGNED",
                "ACCEPTED",
                "IN_PROGRESS",
                "WAITING",
                "COMPLETED",
                "CANCELLED",
            }.issubset(data["overall"]["counts"].keys())
        )
        self.assertTrue({"HIGH", "MEDIUM", "LOW"}.issubset(data["tickets_by_priority"].keys()))
        self.assertIn("UNSPECIFIED", data["tickets_by_close_reason"])
        for reason, counts in data["sla_breaches_by_reason"].items():
            self.assertIn(reason, data["tickets_by_close_reason"])
            self.assertTrue({"response", "completion"}.issubset(counts.keys()))
        for master in data["masters"]:
            self.assertTrue({"id", "name", "total", "counts", "avg_close_sec", "median_close_sec"}.issubset(master.keys()))
