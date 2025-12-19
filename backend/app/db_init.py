# backend/app/db_init.py

from .db import Base, engine
from . import models  # ensures SQLAlchemy loads Conversation + Message classes

def init_db():
    """
    Creates database tables if they do not already exist.
    This function is safe to run multiple times.
    """
    Base.metadata.create_all(bind=engine)
