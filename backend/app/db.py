# backend/app/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# DB will live in data/chat.db at project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "chat.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# For SQLite + multithreaded apps like Streamlit:
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}, 
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
