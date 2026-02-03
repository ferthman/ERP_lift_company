import unittest
import uuid
from datetime import datetime, timezone, timedelta

from liftcrm import create_app, config
from liftcrm.db import SessionLocal, Ticket, TicketComment, User


class TechnicianHistoryTest(unittest.TestCase):
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

    def logout(self):
        self.client.post("/api/logout")

    def create_master_and_tech(self, label):
        res = self.client.post("/api/masters", json={"name": f"Мастер {label}"})
        self.assertEqual(res.status_code, 201)
        master_id = res.get_json()["id"]
        role_res = self.client.post(
            f"/api/masters/{master_id}/assign-role",
            json={"role": "TECHNICIAN", "username": f"tech_{label}"},
        )
        self.assertEqual(role_res.status_code, 200)
        payload = role_res.get_json()
        return master_id, payload["username"], payload["temp_password"]

    def create_ticket(self, object_name):
        res = self.client.post(
            "/api/tickets",
            json={"object_name": object_name, "lat": 43.2, "lon": 76.9, "description": "History"},
        )
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def test_history_scoped_to_technician(self):
        label = uuid.uuid4().hex[:6]
        master_one, tech_one, pass_one = self.create_master_and_tech(f"{label}_a")
        master_two, tech_two, pass_two = self.create_master_and_tech(f"{label}_b")
        ticket_one = self.create_ticket("Tech One Ticket")
        ticket_two = self.create_ticket("Tech Two Ticket")
        closed_time = datetime(2026, 1, 10, tzinfo=timezone.utc)

        with SessionLocal() as db:
            t_one = db.get(Ticket, ticket_one)
            t_one.assigned_master_id = master_one
            t_one.status = "COMPLETED"
            t_one.completed_at = closed_time
            t_one.updated_at = closed_time

            t_two = db.get(Ticket, ticket_two)
            t_two.assigned_master_id = master_two
            t_two.status = "CANCELLED"
            t_two.cancelled_at = closed_time
            t_two.updated_at = closed_time
            db.commit()

        self.logout()
        self.login(tech_one, pass_one)
        res = self.client.get("/api/me/history")
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["items"]
        ids = {item["ticket_id"] for item in items}
        self.assertIn(ticket_one, ids)
        self.assertNotIn(ticket_two, ids)

        self.logout()
        self.login(tech_two, pass_two)
        res = self.client.get("/api/me/history")
        self.assertEqual(res.status_code, 200)
        ids = {item["ticket_id"] for item in res.get_json()["items"]}
        self.assertIn(ticket_two, ids)
        self.assertNotIn(ticket_one, ids)

    def test_history_date_range_filters(self):
        label = uuid.uuid4().hex[:6]
        master_id, tech_user, tech_pass = self.create_master_and_tech(label)
        ticket_early = self.create_ticket("Early")
        ticket_late = self.create_ticket("Late")

        with SessionLocal() as db:
            early = db.get(Ticket, ticket_early)
            early.assigned_master_id = master_id
            early.status = "COMPLETED"
            early.completed_at = datetime(2026, 1, 5, tzinfo=timezone.utc)
            early.updated_at = early.completed_at

            late = db.get(Ticket, ticket_late)
            late.assigned_master_id = master_id
            late.status = "COMPLETED"
            late.completed_at = datetime(2026, 2, 5, tzinfo=timezone.utc)
            late.updated_at = late.completed_at
            db.commit()

        self.logout()
        self.login(tech_user, tech_pass)
        res = self.client.get("/api/me/history?date_from=2026-02-01&date_to=2026-02-28")
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["items"]
        ids = {item["ticket_id"] for item in items}
        self.assertIn(ticket_late, ids)
        self.assertNotIn(ticket_early, ids)

    def test_timeline_permissions_and_comments(self):
        label = uuid.uuid4().hex[:6]
        master_id, tech_user, tech_pass = self.create_master_and_tech(f"{label}_a")
        _other_master_id, other_user, other_pass = self.create_master_and_tech(f"{label}_b")
        ticket_id = self.create_ticket("Timeline Ticket")
        comment_time = datetime.now(timezone.utc) - timedelta(hours=1)

        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            ticket.assigned_master_id = master_id
            ticket.status = "COMPLETED"
            ticket.completed_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
            ticket.updated_at = ticket.completed_at
            tech_user_id = db.query(User.id).filter(User.username == tech_user).scalar()
            comment = TicketComment(
                ticket_id=ticket_id,
                user_id=tech_user_id,
                body="Комментарий мастера",
                created_at=comment_time,
            )
            db.add(comment)
            db.commit()

        self.logout()
        self.login(other_user, other_pass)
        res = self.client.get(f"/api/me/tickets/{ticket_id}/timeline")
        self.assertEqual(res.status_code, 403)

        self.logout()
        self.login(tech_user, tech_pass)
        res = self.client.get(f"/api/me/tickets/{ticket_id}/timeline")
        self.assertEqual(res.status_code, 200)
        timeline = res.get_json()
        comment_events = [item for item in timeline if item["type"] == "COMMENT"]
        self.assertTrue(any(event["body"] == "Комментарий мастера" for event in comment_events))
