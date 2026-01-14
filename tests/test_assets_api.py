import unittest
import uuid

from liftcrm import create_app, config


class AssetsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        self.client = self.app.test_client()
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def login_master(self):
        return self.login("master1", config.MASTER_PASSWORD)

    def create_asset(self, payload):
        res = self.client.post("/api/assets", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()

    def unique_serial(self, prefix):
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    def test_assets_crud_search_export(self):
        serial = self.unique_serial("SN-1001")
        asset = self.create_asset(
            {
                "address": "Алматы, пр. Абая 10",
                "entrance": "2",
                "lift_label": "Lift A",
                "serial_no": serial,
                "lat": 43.25,
                "lon": 76.95,
            }
        )
        asset_id = asset["id"]

        res = self.client.get("/api/assets")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(item["id"] == asset_id for item in res.get_json()))

        res = self.client.get(f"/api/assets?search={serial}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(item["id"] == asset_id for item in res.get_json()))

        res = self.client.patch(f"/api/assets/{asset_id}", json={"status": "INACTIVE", "entrance": "3"})
        self.assertEqual(res.status_code, 200)
        updated = res.get_json()
        self.assertEqual(updated["status"], "INACTIVE")
        self.assertEqual(updated["entrance"], "3")

        csv_res = self.client.get("/api/assets/export.csv")
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("text/csv", csv_res.headers.get("Content-Type", ""))

        xlsx_res = self.client.get("/api/assets/export.xlsx")
        self.assertEqual(xlsx_res.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            xlsx_res.headers.get("Content-Type", ""),
        )
        self.client.post("/api/logout")
        self.login_master()
        list_res = self.client.get("/api/assets")
        self.assertEqual(list_res.status_code, 200)

    def test_ticket_create_with_asset(self):
        asset = self.create_asset(
            {
                "address": "Алматы, ул. Толе би 55",
                "entrance": "1",
                "lift_label": "Lift B",
                "serial_no": self.unique_serial("SN-2002"),
                "lat": 43.21,
                "lon": 76.88,
            }
        )
        res = self.client.post(
            "/api/tickets",
            json={
                "object_name": "Ticket with asset",
                "asset_id": asset["id"],
                "description": "Test",
            },
        )
        self.assertEqual(res.status_code, 201)
        ticket_id = res.get_json()["id"]

        ticket_res = self.client.get(f"/api/tickets/{ticket_id}")
        self.assertEqual(ticket_res.status_code, 200)
        ticket = ticket_res.get_json()
        self.assertEqual(ticket["asset_id"], asset["id"])
        self.assertEqual(ticket["address"], asset["address"])
        self.assertAlmostEqual(ticket["lat"], asset["lat"], places=4)
        self.assertAlmostEqual(ticket["lon"], asset["lon"], places=4)
        summary = ticket["asset_summary"]
        self.assertIsNotNone(summary)
        self.assertEqual(summary["serial_no"], asset["serial_no"])
        self.assertEqual(summary["lift_label"], asset["lift_label"])
        self.assertEqual(summary["entrance"], asset["entrance"])
        self.assertEqual(summary["address"], asset["address"])

    def test_ticket_auto_creates_asset(self):
        res = self.client.post(
            "/api/tickets",
            json={
                "object_name": "Auto asset ticket",
                "address": "Алматы, ул. Абылай хана 77",
                "lat": 43.25,
                "lon": 76.9,
            },
        )
        self.assertEqual(res.status_code, 201)
        ticket_id = res.get_json()["id"]

        ticket_res = self.client.get(f"/api/tickets/{ticket_id}")
        self.assertEqual(ticket_res.status_code, 200)
        ticket = ticket_res.get_json()
        self.assertIsNotNone(ticket["asset_id"])

        assets_res = self.client.get("/api/assets?search=Абылай")
        self.assertEqual(assets_res.status_code, 200)
        assets = assets_res.get_json()
        self.assertTrue(any(asset["id"] == ticket["asset_id"] for asset in assets))

    def test_asset_coords_backfilled_from_ticket(self):
        asset = self.create_asset(
            {
                "address": "Алматы, ул. Жибек Жолы 1",
                "lift_label": "Lift C",
                "serial_no": self.unique_serial("SN-3003"),
            }
        )
        res = self.client.post(
            "/api/tickets",
            json={
                "object_name": "Backfill coords",
                "asset_id": asset["id"],
                "lat": 43.2,
                "lon": 76.92,
            },
        )
        self.assertEqual(res.status_code, 201)
        asset_res = self.client.get(f"/api/assets/{asset['id']}")
        self.assertEqual(asset_res.status_code, 200)
        updated = asset_res.get_json()
        self.assertAlmostEqual(updated["lat"], 43.2, places=4)
        self.assertAlmostEqual(updated["lon"], 76.92, places=4)
