# backend/app/db_init.py

from sqlalchemy import inspect, text

from .db import Base, engine
from . import models  # ensures SQLAlchemy loads Conversation + Message classes


def _ensure_meta_column():
    """
    Lightweight migration to add messages.meta JSON column if missing.
    Safe to run repeatedly.
    """
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("messages")]
    if "meta" not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE messages ADD COLUMN meta JSON"))
            conn.commit()


def init_db():
    """
    Creates database tables if they do not already exist.
    This function is safe to run multiple times.
    """
    Base.metadata.create_all(bind=engine)
    _ensure_meta_column()
