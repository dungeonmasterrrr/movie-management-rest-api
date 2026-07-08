from werkzeug.security import generate_password_hash

from src.config import db
from src.models import User


def seed_default_accounts():
    if not db.session.scalar(db.select(User).filter_by(username="admin")):
        db.session.add(
            User(
                username="admin",
                password_hash=generate_password_hash("admin"),
                role="admin",
            )
        )

    if not db.session.scalar(db.select(User).filter_by(username="user")):
        db.session.add(
            User(
                username="user",
                password_hash=generate_password_hash("user"),
                role="user",
            )
        )

    db.session.commit()
