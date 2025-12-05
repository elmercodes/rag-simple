import streamlit as st

import os
import sys

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)  # one level up from frontend
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from backend.app.db import SessionLocal, engine
from backend.app.db_init import init_db
from backend.app.models import Conversation, Message

init_db()   ### build the file once db schema is decided, won't work till file built

st.title("Converse With Your Documents")