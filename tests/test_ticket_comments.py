import json
import unittest
import uuid

from werkzeug.security import generate_password_hash

from liftcrm import config, create_app
from liftcrm.db import AuditLog, Master, SessionLocal, Ticket, TicketComment, User
from liftcrm.utils.rate_limit import clear_rate_limits
from liftcrm.utils.roles import ROLE_TECHNICIAN


class TicketCommentsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app()
        app.config["TESTING"] = True
        cls.app = app

    def setUp(self):
        clear_rate_limits()
        self.client = self.app.test_client()
        self.tech_password = "ticket-comment-tech-pass"
        self.tech_username = f"ticket_comment_tech_{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            master = Master(name=f"Comment master {self.tech_username}", is_active=1)
            db.add(master)
            db.flush()
            user = User(
                username=self.tech_username,
                password_hash=generate_password_hash(self.tech_password),
                role=ROLE_TECHNICIAN,
                master_id=master.id,
                is_active=1,
            )
            db.add(user)
            db.commit()
            self.master_id = master.id

    def login(self, username, password):
        res = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200)
        return res

    def logout(self):
        self.client.post("/api/logout")

    def create_ticket(self):
        res = self.client.post(
            "/api/tickets",
            json={
                "object_name": f"Comment Ticket {uuid.uuid4().hex[:8]}",
                "lat": 43.238949,
                "lon": 76.889709,
                "description": "Ticket comment test",
            },
        )
        self.assertEqual(res.status_code, 201, res.get_data(as_text=True))
        return res.get_json()["id"]

    def test_admin_can_add_desktop_comment_and_comment_is_visible(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()

        res = self.client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"body": "Диспетчер уточнил детали"},
        )
        self.assertEqual(res.status_code, 201)
        created = res.get_json()
        self.assertEqual(created["body"], "Диспетчер уточнил детали")
        self.assertEqual(created["username"], config.ADMIN_USERNAME)

        detail = self.client.get(f"/api/tickets/{ticket_id}")
        self.assertEqual(detail.status_code, 200)
        comments = detail.get_json()["comments"]
        self.assertTrue(any(comment["body"] == "Диспетчер уточнил детали" for comment in comments))

        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            self.assertEqual(ticket.version, 2)
            comment = db.query(TicketComment).filter_by(ticket_id=ticket_id).one()
            self.assertEqual(comment.body, "Диспетчер уточнил детали")
            audit = (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_type == "ticket",
                    AuditLog.entity_id == ticket_id,
                    AuditLog.action == "COMMENT",
                )
                .one()
            )
            diff = json.loads(audit.diff_json)
            self.assertEqual(diff["new"]["comment_id"], comment.id)
            self.assertEqual(diff["new"]["body"], "Диспетчер уточнил детали")

    def test_dispatcher_can_comment_but_technician_and_anonymous_cannot(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()
        self.logout()

        self.login(config.DISPATCHER_USERNAME, config.DISPATCHER_PASSWORD)
        dispatcher_res = self.client.post(f"/api/tickets/{ticket_id}/comments", json={"body": "Комментарий диспетчера"})
        self.assertEqual(dispatcher_res.status_code, 201)
        self.logout()

        self.login(self.tech_username, self.tech_password)
        tech_res = self.client.post(f"/api/tickets/{ticket_id}/comments", json={"body": "Комментарий мастера"})
        self.assertEqual(tech_res.status_code, 403)
        self.logout()

        anon_res = self.client.post(f"/api/tickets/{ticket_id}/comments", json={"body": "Аноним"})
        self.assertEqual(anon_res.status_code, 401)

    def test_empty_and_archived_ticket_comments_are_rejected(self):
        self.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        ticket_id = self.create_ticket()

        empty_res = self.client.post(f"/api/tickets/{ticket_id}/comments", json={"body": "   "})
        self.assertEqual(empty_res.status_code, 400)

        archive_res = self.client.post(f"/api/tickets/{ticket_id}/archive")
        self.assertEqual(archive_res.status_code, 200)

        archived_res = self.client.post(f"/api/tickets/{ticket_id}/comments", json={"body": "После архива"})
        self.assertEqual(archived_res.status_code, 400)
