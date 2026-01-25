import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from werkzeug.security import generate_password_hash

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Asset, Ticket, TicketComment, User, Master, init_db
from liftcrm.utils.audit import log_audit
from liftcrm.utils.rate_limit import clear_rate_limits


class LiftHistoryApiTest(unittest.TestCase):
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
                master = Master(name="Мастер истории")
                db.add(master)
                db.commit()
                db.refresh(master)
            if db.query(User).filter_by(username="history_tech").first() is None:
                db.add(
                    User(
                        username="history_tech",
                        password_hash=generate_password_hash("techpass"),
                        role="technician",
                        master_id=master.id,
                        is_active=1,
                    )
                )
            if db.query(User).filter_by(username="history_dispatcher").first() is None:
                db.add(
                    User(
                        username="history_dispatcher",
                        password_hash=generate_password_hash("disppass"),
                        role="dispatcher",
                        is_active=1,
                    )
                )
            db.commit()

    def setUp(self):
        clear_rate_limits()
        self.client = self.app.test_client()

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def create_asset_with_tickets(self):
        token = uuid4().hex[:6]
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            admin = db.query(User).filter_by(username=config.ADMIN_USERNAME).first()
            asset = Asset(
                address=f"Алматы, ул. История {token}",
                entrance="1",
                lift_label=f"Лифт {token}",
                serial_no=f"SN-{token}",
                status="ACTIVE",
            )
            db.add(asset)
            db.commit()
            db.refresh(asset)

            ticket_one_created = now - timedelta(days=5)
            ticket_two_created = now - timedelta(days=20)
            ticket_one = Ticket(
                object_name=f"Ticket A {token}",
                address=asset.address,
                lat=43.2,
                lon=76.9,
                status="COMPLETED",
                asset_id=asset.id,
                created_at=ticket_one_created,
            )
            ticket_two = Ticket(
                object_name=f"Ticket B {token}",
                address=asset.address,
                lat=43.2,
                lon=76.9,
                status="CANCELLED",
                asset_id=asset.id,
                created_at=ticket_two_created,
            )
            db.add_all([ticket_one, ticket_two])
            db.commit()
            db.refresh(ticket_one)
            db.refresh(ticket_two)

            comment_recent = TicketComment(
                ticket_id=ticket_one.id,
                user_id=admin.id,
                body="Замена троса",
                created_at=now - timedelta(days=1),
            )
            comment_old = TicketComment(
                ticket_id=ticket_two.id,
                user_id=admin.id,
                body="Проверка двери",
                created_at=now - timedelta(days=10),
            )
            db.add_all([comment_recent, comment_old])
            db.commit()

            accepted_at = ticket_one_created + timedelta(minutes=20)
            in_progress_at = ticket_one_created + timedelta(minutes=40)
            waiting_at = ticket_one_created + timedelta(minutes=60)
            resumed_at = ticket_one_created + timedelta(minutes=120)
            completed_at = ticket_one_created + timedelta(minutes=180)
            ticket_one.accepted_at = accepted_at
            ticket_one.waiting_at = waiting_at
            ticket_one.completed_at = completed_at
            db.commit()

            def add_status_event(ts, old_status, new_status, waiting_reason=None, ticket_id=None):
                entry = log_audit(
                    db,
                    entity_type="ticket",
                    entity_id=ticket_id or ticket_one.id,
                    action="STATUS_CHANGE",
                    actor_user_id=admin.id,
                    old={"status": old_status},
                    new={"status": new_status, "waiting_reason": waiting_reason},
                )
                entry.created_at = ts.isoformat()

            add_status_event(in_progress_at, "NEW", "IN_PROGRESS")
            add_status_event(waiting_at, "IN_PROGRESS", "WAITING", waiting_reason="Ожидание запчастей")
            add_status_event(resumed_at, "WAITING", "IN_PROGRESS")
            add_status_event(completed_at, "IN_PROGRESS", "COMPLETED")
            waiting_two_at = ticket_two_created + timedelta(hours=1)
            cancelled_two_at = ticket_two_created + timedelta(hours=3)
            add_status_event(
                waiting_two_at,
                "NEW",
                "WAITING",
                waiting_reason="Ожидаем доступ",
                ticket_id=ticket_two.id,
            )
            cancel_entry = log_audit(
                db,
                entity_type="ticket",
                entity_id=ticket_two.id,
                action="CANCEL",
                actor_user_id=admin.id,
                old={"status": "WAITING"},
                new={"close_reason": "NO_ACCESS"},
            )
            cancel_entry.created_at = cancelled_two_at.isoformat()
            db.commit()

            return (
                asset.id,
                ticket_one.id,
                ticket_two.id,
                ticket_one_created,
                ticket_two_created,
                comment_recent.created_at,
                comment_old.created_at,
            )

    def test_permissions(self):
        asset_id, _, _, _, _, _, _ = self.create_asset_with_tickets()

        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        admin_res = self.client.get(f"/api/lifts/{asset_id}/history")
        self.assertEqual(admin_res.status_code, 200)

        self.client.post("/api/logout")
        self.login("history_dispatcher", "disppass")
        disp_res = self.client.get(f"/api/lifts/{asset_id}/history")
        self.assertEqual(disp_res.status_code, 200)

        self.client.post("/api/logout")
        self.login("history_tech", "techpass")
        tech_res = self.client.get(f"/api/lifts/{asset_id}/history")
        self.assertEqual(tech_res.status_code, 403)

    def test_history_ordering_and_contains_tickets(self):
        asset_id, ticket_one, ticket_two, _, _, _, _ = self.create_asset_with_tickets()
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

        res = self.client.get(f"/api/lifts/{asset_id}/history")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        tickets = payload["tickets"]
        self.assertGreater(len(tickets), 1)
        ids = {item["ticket"]["id"] for item in tickets}
        self.assertIn(ticket_one, ids)
        self.assertIn(ticket_two, ids)
        self.assertEqual(tickets[0]["ticket"]["id"], ticket_one)
        metrics = tickets[0]["summary"]["metrics"]
        self.assertIn("response_seconds", metrics)
        self.assertIn("repair_seconds", metrics)
        self.assertIn("downtime_seconds", metrics)
        self.assertIsNotNone(metrics["response_seconds"])
        ticket_two_entry = next(item for item in tickets if item["ticket"]["id"] == ticket_two)
        other_metrics = ticket_two_entry["summary"]["metrics"]
        self.assertIn("response_seconds", other_metrics)
        self.assertEqual(other_metrics["downtime_seconds"], 2 * 60 * 60)

    def test_filters_q_and_date_range(self):
        asset_id, ticket_one, _, ticket_one_created, _, _, _ = self.create_asset_with_tickets()
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

        q_res = self.client.get(f"/api/lifts/{asset_id}/history?q=троса")
        self.assertEqual(q_res.status_code, 200)
        q_items = q_res.get_json()["tickets"]
        self.assertEqual(len(q_items), 1)
        self.assertEqual(q_items[0]["ticket"]["id"], ticket_one)

        start_date = (ticket_one_created - timedelta(days=1)).date().isoformat()
        end_date = (ticket_one_created + timedelta(days=1)).date().isoformat()
        date_res = self.client.get(f"/api/lifts/{asset_id}/history?from={start_date}&to={end_date}")
        self.assertEqual(date_res.status_code, 200)
        date_items = date_res.get_json()["tickets"]
        self.assertTrue(all(item["ticket"]["id"] == ticket_one for item in date_items))

    def test_history_page_includes_asset_id_data_attribute(self):
        asset_id, _, _, _, _, _, _ = self.create_asset_with_tickets()
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)

        res = self.client.get(f"/lifts/{asset_id}")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn(f'data-lift-id="{asset_id}"', body)
        self.assertIn("История", body)
        self.assertIn("/static/lift_detail.js", body)
