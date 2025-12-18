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

from backend.app.db import SessionLocal, engine
from backend.app.db_init import init_db         
from backend.app.models import Conversation, Message  
from backend.app.rerank import rerank
from backend.app.retrieval_policy import classify_intent, preferred_sections, should_hard_filter
from backend.app.vectorstore import ingest_file, retrieve_hits, build_context_and_sources
from backend.app.verification import verify_answer



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
            time.sleep(1.5)  


# ------------------------------------------------------------------------------
# STREAMLIT APP
# ------------------------------------------------------------------------------

st.title("Converse With Your Documents")

# ---------- Sidebar: conversations ----------
st.sidebar.header("Documents")

st.sidebar.caption(
    "💡 Tip: For best results, wait for the AI to finish responding "
    "before renaming or switching conversations. If a response stops, "
    "refresh and resend your last message."
)

uploaded_files = st.sidebar.file_uploader(
    "Upload files",
    type=["pdf", "txt", "docx"],
    accept_multiple_files=True,
)

if uploaded_files:
    raw_dir = os.path.join(PROJECT_ROOT, "data", "raw")
    os.makedirs(raw_dir, exist_ok=True)

    for f in uploaded_files:
        save_path = os.path.join(raw_dir, f.name)
        with open(save_path, "wb") as out:
            out.write(f.read())

        # Ingest into Chroma
        doc_id = ingest_file(save_path)
        st.sidebar.success(f"Ingested {f.name} (doc_id={doc_id[:8]}...)")


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

    chat_history = [
        {"role": m.role, "content": m.content}
        for m in trimmed
    ]

    # -------------------- Retrieval policy (intent -> sections) --------------------
    intent = classify_intent(prompt)
    preferred = preferred_sections(intent)

    hard_sections = None
    if should_hard_filter(intent) and preferred:
        # hard filter only for intents we consider "safe" to restrict
        hard_sections = preferred

    # Retrieve more candidates (policy-aware)
    hits = retrieve_hits(
        prompt,
        k=30,
        intent=intent,
        hard_sections=hard_sections,
        preferred=preferred,
    )

    # Rerank AFTER policy scoring
    hits = rerank(prompt, hits, top_n=18)

    # Build context + top page sources + 
    context, sources, evidence_hits = build_context_and_sources(hits, top_pages=2)

    try:
        with st.chat_message("assistant"):
            placeholder = st.empty()

            # ---------------- PASS 1: Generate best-effort paragraph from evidence ----------------
            answer_system = (
                "You are a helpful assistant answering questions using the provided document excerpts.\n"
                "Write ONE clear paragraph.\n"
                "You MAY use common sense to connect points and make reasonable assumptions IF they are consistent with the excerpts.\n"
                "If you make an assumption, briefly signal it with a phrase like 'Likely' or 'It appears'.\n"
                "Do NOT refuse unless the excerpts contain nothing relevant.\n\n"
                f"DOCUMENT EXCERPTS:\n{context}"
                if context
                else "You are a helpful assistant. No document excerpts were provided."
            )

            answer_messages = [
                {"role": "system", "content": answer_system},
                *chat_history,
                {"role": "user", "content": prompt},
            ]

            stream = call_llm_with_retry(client, answer_messages)
            draft = placeholder.write_stream(stream)

            # ---------------- PASS 2: Less-strict check (answered? supported enough?) ----------------
            final_answer, vdebug = verify_answer(
                client=client,
                model=st.session_state["openai_model"],
                question=prompt,
                draft=draft,
                context=context,
                evidence_hits=evidence_hits,
                refusal_text="I can’t find a supported answer in the provided document excerpts.",
            )

            placeholder.markdown(final_answer)

            # ---------------- Sources (dedupe pages so you don't show same page twice) ----------------
            if sources:
                st.markdown("### 📌 Sources")
                seen = set()
                for s in sources:
                    key = (s["filename"], s["page"])
                    if key in seen:
                        continue
                    seen.add(key)
                    st.markdown(f"- **{s['filename']}** — page {s['page']}")

            # Optional: verifier debug in sidebar
            st.sidebar.write(
                f"Verifier: verdict={vdebug.get('verdict')} | confidence={vdebug.get('confidence')}"
            )

            with st.expander("Verifier details (debug)"):
                st.code(vdebug.get("raw", "")[:2000])

            # --- SHOW RETRIEVAL DEBUG (EXCERPTS) ---
            if hits:
                st.markdown("### 🔍 Retrieved evidence")
                st.caption(
                    f"Intent: `{intent}` | Preferred: {preferred or 'None'} | "
                    f"Hard filter: {hard_sections or 'None'}"
                )
                for h in hits[:3]:
                    st.markdown(
                        f"**{h['filename']} – page {h['page']} – `{h.get('section','other')}`** "
                        f"(vec_score {h['score']:.3f} | rerank {h.get('rerank_score', 0):.3f})\n\n"
                        f"> {h['excerpt']}"
                    )

        # Save FINAL answer
        save_message(conversation_id, "assistant", final_answer)


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
