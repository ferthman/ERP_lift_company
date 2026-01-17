from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, func, Text, Index
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from flask_login import UserMixin
from werkzeug.security import generate_password_hash

from . import config
from .utils.users import ROLE_TECHNICIAN

engine = create_engine(f"sqlite:///{config.DB_PATH}", echo=False, future=True)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
)
Base = declarative_base()


class Master(Base):
    __tablename__ = "masters"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    user = relationship("User", uselist=False, back_populates="master")
    tickets = relationship("Ticket", back_populates="assigned_master")


class User(UserMixin, Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin | dispatcher | technician | manager
    master_id = Column(Integer, ForeignKey("masters.id"), nullable=True, unique=True)
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
    address_norm = Column(Text, nullable=True)
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
Index("idx_assets_address_norm", Asset.address_norm)
Index("idx_assets_lat_lon", Asset.lat, Asset.lon)
Index("idx_users_master_id", User.master_id)


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


def ensure_migrations():
    try:
        import sqlite3

        conn = sqlite3.connect(config.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
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
        if "masters" in tables:
            cur.execute("PRAGMA table_info(masters)")
            cols = [r[1] for r in cur.fetchall()]
            if "is_active" not in cols:
                cur.execute("ALTER TABLE masters ADD COLUMN is_active INTEGER DEFAULT 1")
                conn.commit()
            if "phone" not in cols:
                cur.execute("ALTER TABLE masters ADD COLUMN phone TEXT")
                conn.commit()
            if "created_at" not in cols:
                cur.execute("ALTER TABLE masters ADD COLUMN created_at DATETIME")
                conn.commit()
            if "updated_at" not in cols:
                cur.execute("ALTER TABLE masters ADD COLUMN updated_at DATETIME")
                conn.commit()
            now = datetime.now(timezone.utc).isoformat()
            cur.execute("UPDATE masters SET created_at = ? WHERE created_at IS NULL", (now,))
            cur.execute("UPDATE masters SET updated_at = ? WHERE updated_at IS NULL", (now,))
            conn.commit()
        if "users" in tables:
            cur.execute("PRAGMA table_info(users)")
            ucols = [r[1] for r in cur.fetchall()]
            if "master_id" not in ucols:
                cur.execute("ALTER TABLE users ADD COLUMN master_id INTEGER")
                conn.commit()
            cur.execute("UPDATE users SET role = ? WHERE role = ?", (ROLE_TECHNICIAN, "master"))
            conn.commit()
            cur.execute("SELECT id, username, master_id, role FROM users")
            rows = cur.fetchall()
            for user_id, username, master_id, role in rows:
                if role != ROLE_TECHNICIAN or master_id is not None:
                    continue
                if username and username.lower().startswith("master"):
                    suffix = username[6:]
                    if suffix.isdigit():
                        candidate = int(suffix)
                        cur.execute("SELECT id FROM masters WHERE id = ?", (candidate,))
                        if cur.fetchone():
                            cur.execute(
                                "UPDATE users SET master_id = ? WHERE id = ?",
                                (candidate, user_id),
                            )
            conn.commit()
            cur.execute(
                "UPDATE users SET master_id = NULL WHERE role != ? AND master_id IS NOT NULL",
                (ROLE_TECHNICIAN,),
            )
            conn.commit()
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_master_id ON users (master_id)")
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_master_id ON users (master_id) "
                "WHERE master_id IS NOT NULL"
            )
            conn.commit()
        if "tickets" in tables:
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
                    address_norm TEXT NULL,
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
        cur.execute("PRAGMA table_info(assets)")
        acols = [r[1] for r in cur.fetchall()]
        if "address_norm" not in acols:
            cur.execute("ALTER TABLE assets ADD COLUMN address_norm TEXT")
            conn.commit()
        try:
            from .assets.service import normalize_text

            cur.execute("SELECT id, address, address_norm FROM assets")
            rows = cur.fetchall()
            for asset_id, address, address_norm in rows:
                if address_norm and str(address_norm).strip():
                    continue
                normalized = normalize_text(address)
                cur.execute(
                    "UPDATE assets SET address_norm = ? WHERE id = ?",
                    (normalized, asset_id),
                )
            conn.commit()
        except Exception as e:
            print("Failed to backfill assets.address_norm:", e)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_serial_no ON assets (serial_no)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_address ON assets (address)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_address_norm ON assets (address_norm)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_lat_lon ON assets (lat, lon)")
        conn.close()
    except Exception as e:
        print("Migration check failed:", e)
