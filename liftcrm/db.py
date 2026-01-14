from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, func, Text, Index
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from flask_login import UserMixin
from werkzeug.security import generate_password_hash

from . import config
from .utils.security import generate_temp_password

engine = create_engine(f"sqlite:///{config.DB_PATH}", echo=False, future=True)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
)
Base = declarative_base()


class Master(Base):
    __tablename__ = "masters"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    is_active = Column(Integer, default=1)
    user = relationship("User", uselist=False, back_populates="master")
    tickets = relationship("Ticket", back_populates="assigned_master")


class User(UserMixin, Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin | dispatcher | master
    master_id = Column(Integer, ForeignKey("masters.id"), nullable=True)
    master = relationship("Master", back_populates="user")

    def get_id(self):
        return str(self.id)


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    object_name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="NEW")
    priority = Column(String, default="MEDIUM")
    assigned_master_id = Column(Integer, ForeignKey("masters.id"), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    arrived_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    arrival_lat = Column(Float, nullable=True)
    arrival_lon = Column(Float, nullable=True)
    completion_lat = Column(Float, nullable=True)
    completion_lon = Column(Float, nullable=True)
    close_reason = Column(String, nullable=True)
    close_comment = Column(String, nullable=True)
    custom_sla_response_minutes = Column(Integer, nullable=True)
    custom_sla_completion_minutes = Column(Integer, nullable=True)
    assigned_master = relationship("Master", back_populates="tickets")
    attachments = relationship("Attachment", back_populates="ticket", cascade="all, delete-orphan")
    email = Column(String, nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    asset = relationship("Asset", back_populates="tickets")


class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True)
    address = Column(Text, nullable=False)
    entrance = Column(String, nullable=True)
    lift_label = Column(String, nullable=True)
    serial_no = Column(String, nullable=True, unique=True)
    customer_id = Column(Integer, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    tickets = relationship("Ticket", back_populates="asset")


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    filename = Column(String, nullable=False)
    orig_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ticket = relationship("Ticket", back_populates="attachments")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(String, nullable=False)
    diff_json = Column(Text, nullable=False)


Index("idx_audit_log_entity_created", AuditLog.entity_type, AuditLog.entity_id, AuditLog.created_at)
Index("idx_assets_serial_no", Asset.serial_no)
Index("idx_assets_address", Asset.address)
Index("idx_assets_lat_lon", Asset.lat, Asset.lon)


def init_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(Master).count() == 0:
            masters = [Master(name=f"Мастер #{i+1}") for i in range(10)]
            db.add_all(masters)
            db.commit()
        if db.query(User).count() == 0:
            admin = User(
                username=config.ADMIN_USERNAME,
                password_hash=generate_password_hash(config.ADMIN_PASSWORD),
                role="admin",
            )
            disp = User(
                username=config.DISPATCHER_USERNAME,
                password_hash=generate_password_hash(config.DISPATCHER_PASSWORD),
                role="dispatcher",
            )
            db.add_all([admin, disp])
            db.commit()
            for m in db.query(Master).order_by(Master.id).all():
                temp_password = generate_temp_password()
                u = User(
                    username=f"master{m.id}",
                    password_hash=generate_password_hash(temp_password),
                    role="master",
                    master_id=m.id,
                )
                db.add(u)
            db.commit()


def ensure_migrations():
    try:
        import sqlite3

        conn = sqlite3.connect(config.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
        if not cur.fetchone():
            cur.execute(
                """
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor_user_id INTEGER NULL,
                    created_at TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    FOREIGN KEY(actor_user_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                "CREATE INDEX idx_audit_log_entity_created ON audit_log (entity_type, entity_id, created_at)"
            )
            conn.commit()
        cur.execute("PRAGMA table_info(masters)")
        cols = [r[1] for r in cur.fetchall()]
        if "is_active" not in cols:
            cur.execute("ALTER TABLE masters ADD COLUMN is_active INTEGER DEFAULT 1")
            conn.commit()
        cur.execute("PRAGMA table_info(tickets)")
        tcols = [r[1] for r in cur.fetchall()]
        if "priority" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN priority TEXT DEFAULT 'MEDIUM'")
            conn.commit()
        if "email" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN email TEXT")
            conn.commit()
        if "archived_at" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN archived_at DATETIME")
            conn.commit()
        if "close_reason" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN close_reason TEXT")
            conn.commit()
        if "close_comment" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN close_comment TEXT")
            conn.commit()
        if "cancel_reason" in tcols and "close_reason" in tcols:
            cur.execute(
                "UPDATE tickets SET close_reason = cancel_reason "
                "WHERE close_reason IS NULL AND cancel_reason IS NOT NULL"
            )
            conn.commit()
        if "custom_sla_response_minutes" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN custom_sla_response_minutes INTEGER")
            conn.commit()
        if "custom_sla_completion_minutes" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN custom_sla_completion_minutes INTEGER")
            conn.commit()
        if "assigned_at" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN assigned_at DATETIME")
            conn.commit()
        if "asset_id" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN asset_id INTEGER")
            conn.commit()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets'")
        if not cur.fetchone():
            cur.execute(
                """
                CREATE TABLE assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL,
                    entrance TEXT NULL,
                    lift_label TEXT NULL,
                    serial_no TEXT NULL UNIQUE,
                    customer_id INTEGER NULL,
                    lat REAL NULL,
                    lon REAL NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
            conn.commit()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_serial_no ON assets (serial_no)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_address ON assets (address)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_lat_lon ON assets (lat, lon)")
        conn.close()
    except Exception as e:
        print("Migration check failed:", e)
