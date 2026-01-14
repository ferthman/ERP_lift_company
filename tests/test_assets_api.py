import unittest
from uuid import uuid4

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Asset, Ticket
from liftcrm.utils.rate_limit import clear_rate_limits


class AssetsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        clear_rate_limits()
        self.client = self.app.test_client()
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def test_assets_crud_and_search(self):
        serial_no = f"SN-{uuid4().hex[:8]}"
        payload = {
            "address": "Алматы, ул. Абая 10",
            "entrance": "2",
            "lift_label": "Лифт А1",
            "serial_no": serial_no,
            "lat": 43.21,
            "lon": 76.89,
            "status": "ACTIVE",
        }
        res = self.client.post("/api/assets", json=payload)
        self.assertEqual(res.status_code, 201)
        asset_id = res.get_json()["id"]

        list_res = self.client.get("/api/assets?search=абая")
        self.assertEqual(list_res.status_code, 200)
        ids = [a["id"] for a in list_res.get_json()]
        self.assertIn(asset_id, ids)

        patch_res = self.client.patch(f"/api/assets/{asset_id}", json={"status": "INACTIVE"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["status"], "INACTIVE")

    def test_duplicate_serial_rejected(self):
        serial_no = f"SN-{uuid4().hex[:8]}"
        payload = {"address": "Алматы, ул. Сатпаева 1", "serial_no": serial_no}
        res = self.client.post("/api/assets", json=payload)
        self.assertEqual(res.status_code, 201)
        dup_res = self.client.post("/api/assets", json=payload)
        self.assertEqual(dup_res.status_code, 400)

    def test_ticket_asset_linking(self):
        serial_no = f"SN-{uuid4().hex[:8]}"
        asset_res = self.client.post(
            "/api/assets",
            json={"address": "Алматы, ул. Толе Би 5", "serial_no": serial_no, "lat": 43.25, "lon": 76.95},
        )
        self.assertEqual(asset_res.status_code, 201)
        asset_id = asset_res.get_json()["id"]

        ticket_res = self.client.post(
            "/api/tickets",
            json={
                "object_name": "Тест",
                "asset_id": asset_id,
            },
        )
        self.assertEqual(ticket_res.status_code, 201)
        ticket_id = ticket_res.get_json()["id"]

        get_res = self.client.get(f"/api/tickets/{ticket_id}")
        self.assertEqual(get_res.status_code, 200)
        payload = get_res.get_json()
        self.assertEqual(payload["asset_id"], asset_id)
        self.assertEqual(payload["asset_serial_no"], serial_no)

        auto_ticket = self.client.post(
            "/api/tickets",
            json={
                "object_name": "Авто лифт",
                "address": "Алматы, ул. Жибек Жолы 10",
                "lat": 43.22,
                "lon": 76.88,
            },
        )
        self.assertEqual(auto_ticket.status_code, 201)
        auto_ticket_id = auto_ticket.get_json()["id"]
        with SessionLocal() as db:
            ticket = db.get(Ticket, auto_ticket_id)
            self.assertIsNotNone(ticket.asset_id)
            asset = db.get(Asset, ticket.asset_id)
            self.assertIsNotNone(asset)

    def test_assets_export_endpoints(self):
        xlsx_res = self.client.get("/api/assets/export.xlsx")
        self.assertEqual(xlsx_res.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", xlsx_res.content_type)

        csv_res = self.client.get("/api/assets/export.csv")
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("text/csv", csv_res.content_type)

    def test_address_normalization_prevents_duplicates(self):
        token = uuid4().hex[:6]
        messy_address = f"ул.  Кабанбай   батыра  10 кв {token}"
        normalized_address = f"ул Кабанбай батыра 10 кв {token}"
        serial_no = f"SN-{uuid4().hex[:8]}"
        lat_base = 10 + (int(token[:2], 16) / 1000)
        lon_base = 20 + (int(token[2:4], 16) / 1000)
        create_res = self.client.post(
            "/api/assets",
            json={"address": messy_address, "serial_no": serial_no, "lat": lat_base, "lon": lon_base},
        )
        self.assertEqual(create_res.status_code, 201)
        asset_id = create_res.get_json()["id"]
        with SessionLocal() as db:
            before_count = db.query(Asset).count()

        ticket_res = self.client.post(
            "/api/tickets",
            json={
                "object_name": "Тест нормализации",
                "address": normalized_address,
                "lat": lat_base + 0.01,
                "lon": lon_base + 0.01,
            },
        )
        self.assertEqual(ticket_res.status_code, 201)
        ticket_id = ticket_res.get_json()["id"]
        with SessionLocal() as db:
            after_count = db.query(Asset).count()
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.asset_id, asset_id)
        self.assertEqual(before_count, after_count)
