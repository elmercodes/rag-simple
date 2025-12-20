import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

import streamlit as st
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

from backend.app.db import SessionLocal
from backend.app.db_init import init_db, get_default_user_id
from backend.app.models import Conversation, Message, RoutingDecision, Document  
from backend.app.rerank import rerank
from backend.app.retrieval_policy import (
    classify_intent,
    preferred_sections,
    should_hard_filter,
)
from backend.app.vectorstore import ingest_file, retrieve_hits, build_context_and_sources
from backend.app.verification import verify_answer
from backend.app.llm import get_chat_client
import hashlib



# ------------------------------------------------------------------------------
# ONE-TIME DB INIT (per Streamlit process)
# ------------------------------------------------------------------------------

if "db_initialized" not in st.session_state:
    default_user_id = init_db()
    st.session_state["user_id"] = default_user_id
    st.session_state["db_initialized"] = True
elif "user_id" not in st.session_state:
    st.session_state["user_id"] = get_default_user_id()

# ------------------------------------------------------------------------------
# LLM PROVIDERS
# ------------------------------------------------------------------------------

DEFAULT_CHAT_MODELS = {
    "openai": st.secrets.get("OPENAI_MODEL", "gpt-5-nano"),
    "qwen-3": st.secrets.get("QWEN_MODEL_NAME", "qwen-3"),
}

if "chat_models" not in st.session_state:
    st.session_state["chat_models"] = DEFAULT_CHAT_MODELS.copy()

if "llm_provider_by_conversation" not in st.session_state:
    st.session_state["llm_provider_by_conversation"] = {}


@st.cache_resource
def get_cached_chat_client(provider: str):
    return get_chat_client(provider)

# Sticky toggle for RAG vs AI-only (defaults to ON to preserve current behavior)
if "use_documents" not in st.session_state:
    st.session_state["use_documents"] = True

# -------------------- DB Helpers --------------------

@contextmanager
def db_session():
    """Shared session helper to ensure connections are always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_conversation(user_id: int) -> int:
    """Create a new conversation row and return its id."""
    with db_session() as db:
        conv = Conversation(
            user_id=user_id,
            title=f"Session {datetime.now(timezone.utc).isoformat(timespec='minutes')}"
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv.id


def list_conversations(user_id: int, limit: int = 20):
    with db_session() as db:
        return (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .all()
        )


def load_conversation_messages(conversation_id: int, user_id: int):
    with db_session() as db:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return []
        return conv.messages


def save_message(conversation_id: int, role: str, content: str, meta: dict | None = None):
    with db_session() as db:
        msg = Message(
            conversation_id=conversation_id,
            role=role,     # 'user' or 'assistant'
            content=content,
            meta=meta if meta is not None else None,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg


def save_routing_decision(message_id: int, answer_mode: str, reason: str, confidence: float):
    """
    Persist router decision alongside the assistant message for observability.
    """
    with db_session() as db:
        decision = RoutingDecision(
            message_id=message_id,
            answer_mode=answer_mode,
            reason=reason,
            confidence=confidence,
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)
        return decision


def update_conversation_title(conversation_id: int, new_title: str):
    with db_session() as db:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == st.session_state["user_id"],
            )
            .first()
        )
        if conv:
            conv.title = new_title
            db.commit()


def build_retrieved_excerpts(hits: list[dict]) -> list[dict]:
    """
    Normalize the top-3 hits into a stable structure stored on assistant messages.
    """
    excerpts: list[dict] = []
    for idx, h in enumerate(hits[:3], start=1):
        if not h:
            continue
        excerpts.append(
            {
                "rank": idx,
                "attachment_id": h.get("doc_id"),
                "doc_name": h.get("filename"),
                "page": h.get("page"),
                "text": h.get("excerpt"),
                "source_ref": h.get("chunk_index"),
            }
        )
    return excerpts


def list_documents(conversation_id: int, user_id: int) -> list[Document]:
    with db_session() as db:
        return (
            db.query(Document)
            .filter(
                Document.conversation_id == conversation_id,
                Document.user_id == user_id,
            )
            .order_by(Document.created_at.desc())
            .all()
        )


def current_llm_provider(conversation_id: int) -> str:
    providers = st.session_state["llm_provider_by_conversation"]
    if conversation_id not in providers:
        providers[conversation_id] = "openai"
    return providers[conversation_id]


def model_for_provider(provider: str) -> str:
    return st.session_state["chat_models"].get(
        provider,
        st.session_state["chat_models"].get("openai", DEFAULT_CHAT_MODELS["openai"]),
    )


# ------------------------------------------------------------------------------
# OPENAI CALL + RETRY
# ------------------------------------------------------------------------------


def call_llm_with_retry(chat_client, model_name: str, messages, max_retries: int = 2):
    for attempt in range(max_retries):
        try:
            return chat_client.chat_complete(
                model=model_name,
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

# ---------- Sidebar: answer mode toggle ----------
st.sidebar.subheader("Answer mode")
use_documents = st.sidebar.toggle(
    "Use Documents",
    value=st.session_state["use_documents"],
    key="use_documents",
    help="Turn off to answer with the AI only (no document retrieval).",
)
st.sidebar.caption(f"Use Documents is {'ON' if use_documents else 'OFF'}.")

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
user_id = st.session_state["user_id"]

st.sidebar.header("Conversations")

convs = list_conversations(user_id=user_id)

# If no conversations exist yet, create one
if not convs:
    first_id = create_conversation(user_id=user_id)
    convs = list_conversations(user_id=user_id)  # reload with the new one

# Make sure session_state has a conversation_id that exists
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = convs[0].id
else:
    conv_ids = {c.id for c in convs}
    if st.session_state.conversation_id not in conv_ids:
        st.session_state.conversation_id = convs[0].id

# New chat button: create a convo and switch to it
if st.sidebar.button("➕ New chat"):
    new_id = create_conversation(user_id=user_id)
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

conversation_id = st.session_state.conversation_id

# ---- LLM provider per conversation ----
provider_options = ["openai", "qwen-3"]
current_provider = current_llm_provider(conversation_id)
provider_index = provider_options.index(current_provider) if current_provider in provider_options else 0
selected_provider = st.sidebar.selectbox(
    "Language model",
    options=provider_options,
    index=provider_index,
    format_func=lambda v: "OpenAI" if v == "openai" else "qwen-3",
    key=f"llm_provider_{conversation_id}",
    help="Choose which chat model to use for this conversation.",
)
st.session_state["llm_provider_by_conversation"][conversation_id] = selected_provider
st.sidebar.caption(f"Model: {model_for_provider(selected_provider)}")

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

# ---- Documents for current conversation ----
documents = list_documents(conversation_id, user_id)

# ---- Upload validation ----
if uploaded_files:
    raw_dir = os.path.join(PROJECT_ROOT, "data", "raw")
    os.makedirs(raw_dir, exist_ok=True)

    current_count = len(documents)
    existing_hashes = {d.file_hash for d in documents}

    for f in uploaded_files:
        data = f.read()
        file_hash = hashlib.sha256(data).hexdigest()
        is_new_doc = file_hash not in existing_hashes

        # Enforce max 5 docs per conversation in app code to keep UX clear and avoid hard DB failures.
        if is_new_doc and current_count >= 5:
            st.sidebar.warning("Maximum of 5 documents per conversation. Remove one before uploading more.")
            continue

        save_path = os.path.join(raw_dir, f.name)
        with open(save_path, "wb") as out:
            out.write(data)

        doc_id = ingest_file(
            save_path,
            conversation_id=conversation_id,
            user_id=user_id,
            mime_type=f.type,
        )
        st.sidebar.success(f"Ingested {f.name} (doc_id={doc_id[:8]}...)")

        if is_new_doc:
            current_count += 1
            existing_hashes.add(file_hash)

    # refresh list for UI
    documents = list_documents(conversation_id, user_id)

st.sidebar.markdown(f"**Current conversation documents ({len(documents)}/5)**")
if documents:
    for doc in documents:
        st.sidebar.write(f"• {doc.filename}")
else:
    st.sidebar.caption("No documents yet for this chat.")


# ------------------- Main chat area ----------------------

history = load_conversation_messages(conversation_id, user_id)

for msg in history:
    with st.chat_message(msg.role):
        st.write(msg.content)
        if msg.role == "assistant":
            meta = msg.meta or {}
            excerpts = meta.get("retrieved_excerpts") or []
            verdict = (meta.get("verification") or {}).get("verdict")
            # Suppress evidence when the verifier marked the answer unsupported.
            show_evidence = meta.get("used_docs") and excerpts and verdict != "UNSUPPORTED"
            if show_evidence:
                st.markdown("### Context")
                for ex in excerpts:
                    location = ""
                    if ex.get("doc_name"):
                        location = ex["doc_name"]
                        if ex.get("page"):
                            location += f" — page {ex['page']}"
                    prefix = f"{ex.get('rank', 0)})"
                    if location:
                        prefix = f"{ex.get('rank', 0)}) {location}"
                    st.markdown(f"{prefix}\n\n> {ex.get('text', '')}")


# New message from user
prompt = st.chat_input("Ask me something...")

if prompt:
    # Save user message
    save_message(conversation_id, "user", prompt)

    # Show user message
    with st.chat_message("user"):
        st.markdown(prompt)

    llm_provider = current_llm_provider(conversation_id)
    chat_model = model_for_provider(llm_provider)

    # Build history for LLM (trim to last N turns)
    MAX_TURNS = 8
    full_history = load_conversation_messages(conversation_id, user_id)
    trimmed = full_history[-MAX_TURNS:]

    chat_history = [
        {"role": m.role, "content": m.content}
        for m in trimmed
    ]

    # -------------------- Routing: toggle decides RAG vs AI-only --------------------
    answer_mode = "rag" if st.session_state["use_documents"] else "direct"
    mode_reason = (
        "User selected Use Documents toggle."
        if st.session_state["use_documents"]
        else "User turned off Use Documents toggle; retrieval skipped."
    )
    meta_data = {
        "used_docs": bool(st.session_state["use_documents"]),
        "retrieved_excerpts": [],
        "llm_provider": llm_provider,
        "llm_model": chat_model,
    }
    retrieved_excerpts: list[dict] = []

    try:
        chat_client = get_cached_chat_client(llm_provider)
        with st.chat_message("assistant"):
            placeholder = st.empty()

            if answer_mode == "direct":
                direct_system = (
                    "You are a helpful assistant. Answer the user concisely and accurately.\n"
                    "If the question actually requires document-specific facts, ask to look at the uploaded documents."
                )
                direct_messages = [
                    {"role": "system", "content": direct_system},
                    *chat_history,
                    {"role": "user", "content": prompt},
                ]

                stream = call_llm_with_retry(chat_client, chat_model, direct_messages)
                direct_answer = placeholder.write_stream(stream)

                # Subtle note when AI-only mode is selected by the user.
                note = (
                    "_AI-only (documents not used)._"
                    if not st.session_state["use_documents"]
                    else "_Answered without document retrieval._"
                )
                final_answer = f"{direct_answer}\n\n{note}"
                placeholder.markdown(final_answer)

            else:
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
                    user_id=user_id,
                    conversation_id=conversation_id,
                    k=30,
                    intent=intent,
                    hard_sections=hard_sections,
                    preferred=preferred,
                )

                # Rerank AFTER policy scoring
                hits = rerank(prompt, hits, top_n=18)

                # Build context + top page sources +
                context, _sources, evidence_hits = build_context_and_sources(hits, top_pages=3)

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

                stream = call_llm_with_retry(chat_client, chat_model, answer_messages)
                draft = placeholder.write_stream(stream)

                # ---------------- PASS 2: Less-strict check (answered? supported enough?) ----------------
                final_answer, vdebug = verify_answer(
                    chat_client=chat_client,
                    model=chat_model,
                    question=prompt,
                    draft=draft,
                    context=context,
                    evidence_hits=evidence_hits,
                    refusal_text="I can’t find a supported answer in the provided document excerpts.",
                )
                verdict = (vdebug or {}).get("verdict", "UNSUPPORTED")
                confidence = (vdebug or {}).get("confidence", 0.0)
                # Only surface excerpts when the verifier considers the answer supported enough.
                show_evidence = verdict in ("SUPPORTED", "PARTIAL") and bool(evidence_hits)

                placeholder.markdown(final_answer)

                # Hide evidence when the verifier marks the answer unsupported so we don't surface ungrounded context.
                retrieved_excerpts = build_retrieved_excerpts(evidence_hits) if show_evidence else []
                meta_data["retrieved_excerpts"] = retrieved_excerpts
                meta_data["verification"] = {
                    "verdict": verdict,
                    "confidence": confidence,
                }

                # --- Supporting excerpts (user-facing) ---
                if show_evidence and retrieved_excerpts:
                    st.markdown("### Context")
                    for ex in retrieved_excerpts:
                        location = ""
                        if ex.get("doc_name"):
                            location = f"{ex['doc_name']}"
                            if ex.get("page"):
                                location += f" — page {ex['page']}"
                        prefix = f"{ex.get('rank', 0)})"
                        if location:
                            prefix = f"{ex.get('rank', 0)}) {location}"
                        st.markdown(
                            f"{prefix}\n\n> {ex.get('text', '')}"
                        )

        # Save FINAL answer
        assistant_msg = save_message(
            conversation_id,
            "assistant",
            final_answer,
            meta=meta_data,
        )
        save_routing_decision(
            message_id=assistant_msg.id,
            answer_mode=answer_mode,
            reason=mode_reason,
            confidence=1.0,
        )


    except AuthenticationError as e:
        st.error("Authentication failed for the selected language model provider. Check your API keys/base URL.")
        st.exception(e)
    except APIConnectionError:
        st.warning("Lost connection to the language model provider while answering. Please try again.")
    except APIStatusError as e:
        st.error(f"LLM provider returned an error: {e.status_code}")
        st.exception(e)
    except Exception as e:
        st.error("Unexpected error talking to the LLM provider.")
        st.exception(e)
