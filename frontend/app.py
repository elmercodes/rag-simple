import streamlit as st
from datetime import datetime, timezone
import time
from openai import OpenAI
from openai import OpenAI, APIConnectionError, APIStatusError, AuthenticationError


import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

print(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from backend.app.db import SessionLocal, engine
from backend.app.db_init import init_db
from backend.app.models import Conversation, Message

init_db() 

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = "gpt-5-nano"
    

def create_conversation():
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


def load_conversation_messages(conversation_id):
    db = SessionLocal()
    try:
        # Query the conversation row
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()

        # If conversation doesn't exist (rare), return empty list
        if not conv:
            return []

        # conv.messages is automatically retrieved & sorted (because of relationship)
        return conv.messages
    finally:
        db.close()
def save_message(conversation_id, role, content):
    db = SessionLocal()
    try:
        msg = Message(
            conversation_id=conversation_id,
            role=role,     # 'user' or 'assistant'
            content=content
        )

        db.add(msg)     # stage insert
        db.commit()     # write to database
        db.refresh(msg) # populate msg.id and timestamp

        return msg
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
        
from openai import APIConnectionError
import time

def call_llm_with_retry(client, messages, max_retries=2):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=st.session_state["openai_model"],
                messages=messages,
                stream=True,
            )
        except APIConnectionError as e:
            if attempt == max_retries - 1:
                raise  # re-raise after last attempt
            time.sleep(1.5)  # brief backoff and retry
        
################################################################### STREAMLIT BEGINS
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
    # If stored id is no longer in DB, fall back to first
    conv_ids = {c.id for c in convs}
    if st.session_state.conversation_id not in conv_ids:
        st.session_state.conversation_id = convs[0].id

# New chat button: create a convo and switch to it
if st.sidebar.button("➕ New chat"):
    new_id = create_conversation()
    st.session_state.conversation_id = new_id
    st.rerun()

# Determine which index in convs matches the current id
current_id = st.session_state.conversation_id
current_index = next(
    (i for i, c in enumerate(convs) if c.id == current_id),
    0,  # fallback to first
)

# Selectbox is always in sync with conversation_id
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

# Single source of truth for the rest of the app:
conversation_id = st.session_state.conversation_id

history = load_conversation_messages(conversation_id)

for msg in history:
    with st.chat_message(msg.role):
        st.write(msg.content)

# 2) New message from user
if prompt := st.chat_input("Ask me something..."):
    # Save user message to DB
    save_message(conversation_id, "user", prompt)

    # Show user message in UI
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build history for OpenAI from DB (NOT session_state)
    history = load_conversation_messages(conversation_id)
    llm_history = [
        {"role": m.role, "content": m.content}
        for m in history
    ]
    try:
        # 3) Call OpenAI with streaming, just like your original code
        with st.chat_message("assistant"):
        # TRY with retry logic instead of a raw OpenAI call
            stream = call_llm_with_retry(client, llm_history)
            response = st.write_stream(stream)

        save_message(conversation_id, "assistant", response)


    except AuthenticationError as e:
        st.error("OpenAI authentication failed. Check your API key in st.secrets.")
        st.exception(e)
    except APIConnectionError as e:
        st.error("Couldn't reach OpenAI API (network / VPN / DNS issue).")
        st.exception(e)
    except APIStatusError as e:
        st.error(f"OpenAI API returned an error: {e.status_code}")
        st.exception(e)
    except Exception as e:
        st.error("Unexpected error talking to OpenAI.")
        st.exception(e)


