"""Create technician users for masters missing a linked account (dev utility)."""

from werkzeug.security import generate_password_hash

from liftcrm.db import SessionLocal, Master, User
from liftcrm.utils.security import generate_temp_password
from liftcrm.utils.users import ROLE_TECHNICIAN


def _unique_username(db, base):
    candidate = base
    counter = 1
    while db.query(User).filter(User.username == candidate).first():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def main():
    created = []
    with SessionLocal() as db:
        masters = db.query(Master).order_by(Master.id).all()
        for master in masters:
            if db.query(User).filter(User.master_id == master.id).first():
                continue
            username = _unique_username(db, f"master{master.id}")
            temp_password = generate_temp_password()
            user = User(
                username=username,
                password_hash=generate_password_hash(temp_password),
                role=ROLE_TECHNICIAN,
                master_id=master.id,
            )
            db.add(user)
            created.append((master.id, username, temp_password))
        db.commit()
    if not created:
        print("No missing technician users found.")
        return
    print("Created technician users:")
    for master_id, username, temp_password in created:
        print(f"- master_id={master_id} username={username} temp_password={temp_password}")


if __name__ == "__main__":
    main()
