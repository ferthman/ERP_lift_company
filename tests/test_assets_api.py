import io
import unittest
from uuid import uuid4

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Asset, Ticket, User, Master
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

    def post_import(self, content, filename):
        return self.client.post(
            "/api/assets/import",
            data={"file": (io.BytesIO(content), filename)},
            content_type="multipart/form-data",
        )

    def make_csv(self, rows):
        lines = ["address,entrance,lift_label,serial_no,lat,lon,status"]
        lines.extend(rows)
        return ("\n".join(lines) + "\n").encode("utf-8")

    def make_xlsx(self, rows):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["объект", "подъезд", "лифт", "заводской номер", "широта", "долгота", "статус"])
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def create_technician_user(self):
        username = f"tech-{uuid4().hex[:8]}"
        password = "tech-pass"
        with SessionLocal() as db:
            master = Master(name=f"Tech {uuid4().hex[:6]}", is_active=1)
            db.add(master)
            db.flush()
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                role="technician",
                master_id=master.id,
                is_active=1,
            )
            db.add(user)
            db.commit()
        return username, password

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

    def test_admin_can_import_valid_csv(self):
        token = uuid4().hex[:8]
        res = self.post_import(
            self.make_csv([f"Алматы CSV {token},1,A,{token}-CSV,43.21,76.89,ACTIVE"]),
            "assets.csv",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["created"], 1)
        self.assertEqual(payload["updated"], 0)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["invalid"], 0)
        with SessionLocal() as db:
            asset = db.query(Asset).filter_by(serial_no=f"{token}-CSV").first()
            self.assertIsNotNone(asset)
            self.assertEqual(asset.address, f"Алматы CSV {token}")

    def test_admin_can_import_valid_xlsx(self):
        token = uuid4().hex[:8]
        res = self.post_import(
            self.make_xlsx([[f"Алматы XLSX {token}", "2", "B", f"{token}-XLSX", 43.22, 76.90, "INACTIVE"]]),
            "assets.xlsx",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["created"], 1)
        self.assertEqual(payload["invalid"], 0)
        with SessionLocal() as db:
            asset = db.query(Asset).filter_by(serial_no=f"{token}-XLSX").first()
            self.assertIsNotNone(asset)
            self.assertEqual(asset.status, "INACTIVE")

    def test_dispatcher_can_import_assets(self):
        self.client.post("/api/logout")
        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        token = uuid4().hex[:8]
        res = self.post_import(
            self.make_csv([f"Алматы DISP {token},3,C,{token}-DISP,,,ACTIVE"]),
            "dispatcher-assets.csv",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["created"], 1)

    def test_technician_cannot_import_assets(self):
        username, password = self.create_technician_user()
        self.client.post("/api/logout")
        self.login(username, password)
        res = self.post_import(
            self.make_csv([f"Алматы TECH {uuid4().hex[:8]},1,A,{uuid4().hex[:8]},,,ACTIVE"]),
            "technician-assets.csv",
        )
        self.assertEqual(res.status_code, 403)

    def test_anonymous_cannot_import_assets(self):
        client = self.app.test_client()
        res = client.post(
            "/api/assets/import",
            data={"file": (io.BytesIO(self.make_csv(["Алматы Anonymous,1,A,ANON-1,,,ACTIVE"])), "assets.csv")},
            content_type="multipart/form-data",
        )
        self.assertIn(res.status_code, {302, 401})

    def test_invalid_file_type_is_rejected(self):
        res = self.post_import(b"not an asset import", "assets.txt")
        self.assertEqual(res.status_code, 400)
        self.assertIn(".csv or .xlsx", res.get_json()["error"]["message"])

    def test_invalid_coordinates_are_reported(self):
        token = uuid4().hex[:8]
        res = self.post_import(
            self.make_csv([f"Алматы BAD COORD {token},1,A,{token}-BAD,not-a-number,76.89,ACTIVE"]),
            "assets.csv",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["created"], 0)
        self.assertEqual(payload["invalid"], 1)
        self.assertEqual(payload["errors"][0]["row"], 2)
        self.assertEqual(payload["errors"][0]["field"], "lat")

    def test_duplicate_rows_do_not_create_duplicate_assets(self):
        token = uuid4().hex[:8]
        content = self.make_csv(
            [
                f"Алматы DUP {token},1,A,{token}-DUP,43.21,76.89,ACTIVE",
                f"Алматы DUP Changed {token},2,B,{token}-DUP,43.22,76.90,ACTIVE",
            ]
        )
        res = self.post_import(content, "assets.csv")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["created"], 1)
        self.assertEqual(payload["skipped_duplicates"], 1)
        with SessionLocal() as db:
            count = db.query(Asset).filter_by(serial_no=f"{token}-DUP").count()
        self.assertEqual(count, 1)

    def test_composite_duplicate_without_serial_is_skipped(self):
        token = uuid4().hex[:8]
        content = self.make_csv(
            [
                f"Алматы COMPOSITE {token},1,A,,43.21,76.89,ACTIVE",
                f"Алматы COMPOSITE {token},1,A,,43.22,76.90,ACTIVE",
            ]
        )
        res = self.post_import(content, "assets.csv")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["created"], 1)
        self.assertEqual(payload["skipped_duplicates"], 1)

    def test_row_level_errors_and_counts_are_returned(self):
        token = uuid4().hex[:8]
        content = self.make_csv(
            [
                f"Алматы VALID {token},1,A,{token}-VALID,43.21,76.89,ACTIVE",
                f",2,B,{token}-NOADDRESS,43.22,76.90,ACTIVE",
                f"Алматы BAD STATUS {token},3,C,{token}-BADSTATUS,43.23,76.91,BROKEN",
            ]
        )
        res = self.post_import(content, "assets.csv")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["created"], 1)
        self.assertEqual(payload["updated"], 0)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["invalid"], 2)
        self.assertEqual(len(payload["errors"]), 2)
        self.assertEqual({err["row"] for err in payload["errors"]}, {3, 4})
