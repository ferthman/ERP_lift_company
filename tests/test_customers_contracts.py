import importlib
import os
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from werkzeug.security import generate_password_hash

from liftcrm import config, create_app
from liftcrm.db import SessionLocal, Master, User
from liftcrm.utils.rate_limit import clear_rate_limits


class CustomersContractsTest(unittest.TestCase):
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

    def create_technician_user(self):
        username = f"contract-tech-{uuid4().hex[:8]}"
        password = "tech-pass"
        with SessionLocal() as db:
            master = Master(name=f"Contract Tech {uuid4().hex[:6]}", is_active=1)
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

    def create_customer(self, name=None):
        res = self.client.post(
            "/api/customers",
            json={
                "name": name or f"Customer {uuid4().hex[:8]}",
                "contact_person": "Ops Contact",
                "phone": "+77000000000",
                "email": "ops@example.test",
            },
        )
        self.assertEqual(res.status_code, 201)
        return res.get_json()

    def create_contract(self, customer_id, title=None):
        res = self.client.post(
            "/api/contracts",
            json={
                "customer_id": customer_id,
                "contract_number": f"C-{uuid4().hex[:8]}",
                "title": title or "Service contract",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "status": "active",
                "sla_hours_normal": 24,
                "sla_hours_high": 4,
                "sla_hours_emergency": 1,
            },
        )
        self.assertEqual(res.status_code, 201)
        return res.get_json()

    def test_admin_can_create_and_update_customer(self):
        customer = self.create_customer()
        self.assertTrue(customer["is_active"])

        res = self.client.patch(
            f"/api/customers/{customer['id']}",
            json={"name": f"Updated {uuid4().hex[:6]}", "is_active": False, "notes": "Pilot customer"},
        )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertFalse(payload["is_active"])
        self.assertEqual(payload["notes"], "Pilot customer")

    def test_dispatcher_can_manage_customers_and_contracts(self):
        self.client.post("/api/logout")
        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        customer = self.create_customer()
        contract = self.create_contract(customer["id"], title="Dispatcher contract")

        res = self.client.patch(
            f"/api/contracts/{contract['id']}",
            json={"status": "paused", "sla_hours_high": 6},
        )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["status"], "paused")
        self.assertEqual(payload["sla_hours_high"], 6)

    def test_technician_and_anonymous_cannot_manage_customers_contracts(self):
        username, password = self.create_technician_user()
        self.client.post("/api/logout")
        self.login(username, password)
        res = self.client.post("/api/customers", json={"name": "Blocked"})
        self.assertEqual(res.status_code, 403)

        anonymous = self.app.test_client()
        anon_res = anonymous.get("/api/customers")
        self.assertEqual(anon_res.status_code, 401)

    def test_customer_name_is_required(self):
        res = self.client.post("/api/customers", json={"name": " "})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Customer name is required", res.get_json()["error"]["message"])

    def test_contract_validation_returns_400_for_bad_payloads(self):
        missing_customer = self.client.post("/api/contracts", json={"title": "No customer"})
        self.assertEqual(missing_customer.status_code, 400)

        customer = self.create_customer()
        bad_customer = self.client.post("/api/contracts", json={"customer_id": 999999, "title": "Bad"})
        self.assertEqual(bad_customer.status_code, 400)

        bad_dates = self.client.post(
            "/api/contracts",
            json={
                "customer_id": customer["id"],
                "title": "Bad dates",
                "start_date": "2026-12-31",
                "end_date": "2026-01-01",
            },
        )
        self.assertEqual(bad_dates.status_code, 400)

        bad_sla = self.client.post(
            "/api/contracts",
            json={"customer_id": customer["id"], "title": "Bad SLA", "sla_hours_high": 0},
        )
        self.assertEqual(bad_sla.status_code, 400)

    def test_asset_can_be_linked_to_customer_and_contract(self):
        customer = self.create_customer()
        contract = self.create_contract(customer["id"])
        serial = f"CC-{uuid4().hex[:8]}"

        asset_res = self.client.post(
            "/api/assets",
            json={
                "address": f"Алматы contract asset {uuid4().hex[:8]}",
                "serial_no": serial,
                "lat": 43.21,
                "lon": 76.89,
                "customer_id": customer["id"],
                "contract_id": contract["id"],
            },
        )
        self.assertEqual(asset_res.status_code, 201)
        asset = asset_res.get_json()
        self.assertEqual(asset["customer_name"], customer["name"])
        self.assertEqual(asset["contract_title"], contract["title"])

        list_res = self.client.get(f"/api/assets?search={serial}")
        self.assertEqual(list_res.status_code, 200)
        listed = list_res.get_json()[0]
        self.assertEqual(listed["customer_id"], customer["id"])
        self.assertEqual(listed["contract_id"], contract["id"])

    def test_asset_rejects_contract_from_other_customer(self):
        customer_one = self.create_customer()
        customer_two = self.create_customer()
        contract = self.create_contract(customer_one["id"])
        res = self.client.post(
            "/api/assets",
            json={
                "address": f"Алматы mismatch {uuid4().hex[:8]}",
                "customer_id": customer_two["id"],
                "contract_id": contract["id"],
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Contract must belong", res.get_json()["error"]["message"])

    def test_ticket_context_is_derived_from_linked_asset(self):
        customer = self.create_customer()
        contract = self.create_contract(customer["id"])
        asset_res = self.client.post(
            "/api/assets",
            json={
                "address": f"Алматы ticket context {uuid4().hex[:8]}",
                "serial_no": f"CTX-{uuid4().hex[:8]}",
                "lat": 43.22,
                "lon": 76.9,
                "customer_id": customer["id"],
                "contract_id": contract["id"],
            },
        )
        self.assertEqual(asset_res.status_code, 201)
        asset_id = asset_res.get_json()["id"]

        ticket_res = self.client.post("/api/tickets", json={"object_name": "Context ticket", "asset_id": asset_id})
        self.assertEqual(ticket_res.status_code, 201)
        ticket_id = ticket_res.get_json()["id"]
        detail = self.client.get(f"/api/tickets/{ticket_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        self.assertEqual(payload["customer_name"], customer["name"])
        self.assertEqual(payload["contract_title"], contract["title"])
        self.assertEqual(payload["contract_status"], "active")

    def test_existing_ticket_flow_still_works_without_customer_contract(self):
        ticket_res = self.client.post(
            "/api/tickets",
            json={
                "object_name": f"Legacy ticket {uuid4().hex[:8]}",
                "lat": 43.238949,
                "lon": 76.889709,
                "description": "No customer context",
            },
        )
        self.assertEqual(ticket_res.status_code, 201)
        detail = self.client.get(f"/api/tickets/{ticket_res.get_json()['id']}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        self.assertIn("customer_id", payload)
        self.assertIsNone(payload["customer_id"])
        self.assertIsNone(payload["contract_id"])


class CustomersContractsMigrationTest(unittest.TestCase):
    def test_fresh_db_creates_customer_contract_tables_and_asset_links(self):
        original_db_path = config.DB_PATH
        original_archive_path = config.ARCHIVE_PATH
        original_upload_folder = config.UPLOAD_FOLDER
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, "fresh-customers.db")
                config.DB_PATH = db_path
                config.ARCHIVE_PATH = os.path.join(tmpdir, "archive.xlsx")
                config.UPLOAD_FOLDER = os.path.join(tmpdir, "uploads")

                import liftcrm.db as db_module
                import liftcrm.tickets.service as service_module

                importlib.reload(db_module)
                importlib.reload(service_module)
                db_module.init_db()
                db_module.ensure_migrations()

                conn = sqlite3.connect(db_path)
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = {row[0] for row in cur.fetchall()}
                    self.assertIn("customers", tables)
                    self.assertIn("contracts", tables)
                    cur.execute("PRAGMA table_info(assets)")
                    asset_cols = {row[1] for row in cur.fetchall()}
                    self.assertIn("customer_id", asset_cols)
                    self.assertIn("contract_id", asset_cols)
                finally:
                    conn.close()
        finally:
            config.DB_PATH = original_db_path
            config.ARCHIVE_PATH = original_archive_path
            config.UPLOAD_FOLDER = original_upload_folder
            import liftcrm.db as db_module
            import liftcrm.tickets.service as service_module

            importlib.reload(db_module)
            importlib.reload(service_module)
