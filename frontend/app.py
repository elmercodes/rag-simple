import os
import sys
import time
from datetime import datetime, timezone

import streamlit as st
from openai import OpenAI
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
)

# ------------------------------------------------------------------------------
# PATH / IMPORTS
# ------------------------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from backend.app.db import SessionLocal, engine  # noqa: E402,F401
from backend.app.db_init import init_db          # noqa: E402
from backend.app.models import Conversation, Message  # noqa: E402

# ------------------------------------------------------------------------------
# ONE-TIME DB INIT (per Streamlit process)
# ------------------------------------------------------------------------------

if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

# ------------------------------------------------------------------------------
# OPENAI CLIENT
# ------------------------------------------------------------------------------

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = "gpt-5-nano"

# ------------------------------------------------------------------------------
# DB HELPERS
# ------------------------------------------------------------------------------


def create_conversation() -> int:
    """Create a new conversation row and return its id."""
    db = SessionLocal()
    try:
        conv = Conversation(
            title=f"Session {datetime.now(timezone.utc).isoformat(timespec='minutes')}"
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv.id
    finally:
        db.close()


def list_conversations(limit: int = 20):
    db = SessionLocal()
    try:
        return (
            db.query(Conversation)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .all()
        )
    finally:
        db.close()


def load_conversation_messages(conversation_id: int):
    db = SessionLocal()
    try:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conv:
            return []
        return conv.messages
    finally:
        db.close()


def save_message(conversation_id: int, role: str, content: str):
    db = SessionLocal()
    try:
        msg = Message(
            conversation_id=conversation_id,
            role=role,     # 'user' or 'assistant'
            content=content,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg
    finally:
        db.close()


def update_conversation_title(conversation_id: int, new_title: str):
    db = SessionLocal()
    try:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if conv:
            conv.title = new_title
            db.commit()
    finally:
        db.close()


# ------------------------------------------------------------------------------
# OPENAI CALL + RETRY
# ------------------------------------------------------------------------------


def call_llm_with_retry(client: OpenAI, messages, max_retries: int = 2):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=st.session_state["openai_model"],
                messages=messages,
                stream=True,
            )
        except APIConnectionError:
            if attempt == max_retries - 1:
                raise
            time.sleep(1.5)  # brief backoff


# ------------------------------------------------------------------------------
# STREAMLIT APP
# ------------------------------------------------------------------------------

st.title("Converse With Your Documents")

# ---------- Sidebar: conversations ----------
st.sidebar.header("Conversations")

convs = list_conversations()

# If no conversations exist yet, create one
if not convs:
    first_id = create_conversation()
    convs = list_conversations()  # reload with the new one

# Make sure session_state has a conversation_id that exists
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = convs[0].id
else:
    conv_ids = {c.id for c in convs}
    if st.session_state.conversation_id not in conv_ids:
        st.session_state.conversation_id = convs[0].id

# New chat button: create a convo and switch to it
if st.sidebar.button("➕ New chat"):
    new_id = create_conversation()
    st.session_state.conversation_id = new_id
    st.rerun()

current_id = st.session_state.conversation_id
current_index = next(
    (i for i, c in enumerate(convs) if c.id == current_id),
    0,  # fallback to first
)

selected_conv = st.sidebar.selectbox(
    "Select a conversation",
    options=convs,
    index=current_index,
    format_func=lambda c: f"{c.title or 'Untitled'} (id {c.id})",
)

# If user chose a different conversation, update state and rerun
if selected_conv.id != current_id:
    st.session_state.conversation_id = selected_conv.id
    st.rerun()

# ---- Rename conversation ----
st.sidebar.subheader("Rename conversation")

new_title = st.sidebar.text_input(
    "Title",
    value=selected_conv.title or "",
    key="conv_title_input",
)

if st.sidebar.button("Save title"):
    cleaned_title = new_title.strip() or "Untitled"
    update_conversation_title(selected_conv.id, cleaned_title)
    st.rerun()

st.sidebar.caption(
    "💡 Tip: For best results, wait for the AI to finish responding "
    "before renaming or switching conversations. If a response stops, "
    "refresh and resend your last message."
)

# ------------------- Main chat area ----------------------

conversation_id = st.session_state.conversation_id

history = load_conversation_messages(conversation_id)

for msg in history:
    with st.chat_message(msg.role):
        st.write(msg.content)


# New message from user
prompt = st.chat_input("Ask me something...")

if prompt:
    # Save user message
    save_message(conversation_id, "user", prompt)

    # Show user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build history for LLM (trim to last N turns)
    MAX_TURNS = 8
    full_history = load_conversation_messages(conversation_id)
    trimmed = full_history[-MAX_TURNS:]

    llm_history = [
        {"role": m.role, "content": m.content}
        for m in trimmed
    ]

    # Optional debug of prompt size
    total_chars = sum(len(m["content"]) for m in llm_history)
    total_msgs = len(llm_history)
    st.sidebar.write(f"DEBUG: {total_msgs} msgs, ~{total_chars} chars total")

    try:
        with st.chat_message("assistant"):
            stream = call_llm_with_retry(client, llm_history)
            response = st.write_stream(stream)

        save_message(conversation_id, "assistant", response)

    except AuthenticationError as e:
        st.error("OpenAI authentication failed. Check your API key in st.secrets.")
        st.exception(e)
    except APIConnectionError:
        st.warning("Lost connection to OpenAI while answering. Please try again.")
    except APIStatusError as e:
        st.error(f"OpenAI API returned an error: {e.status_code}")
        st.exception(e)
    except Exception as e:
        st.error("Unexpected error talking to OpenAI.")
        st.exception(e)
