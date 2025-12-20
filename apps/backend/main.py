import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.db_init import get_default_user_id, init_db
from backend.app.llm import get_chat_client
from backend.app.models import Attachment, Conversation, Message, RoutingDecision, UserSettings
from backend.app.rerank import rerank
from backend.app.retrieval_policy import classify_intent, preferred_sections, should_hard_filter
from backend.app.vectorstore import (
    build_context_and_sources,
    delete_conversation_embeddings,
    ingest_file,
    retrieve_hits,
)
from backend.app.verification import verify_answer


app = FastAPI(title="RAG Backend API")

# ---- CORS ----
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---- Configuration ----
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")
DEFAULT_VLLM_MODEL = os.getenv("VLLM_MODEL_NAME", "qwen-3")
MAX_TURNS = int(os.getenv("MAX_TURNS", "8"))
MAX_PINNED = 5
MAX_ATTACHMENTS = 5
SUPPORTED_ATTACHMENT_TYPES = {"pdf", "txt", "docx"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RAW_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
os.makedirs(RAW_DATA_DIR, exist_ok=True)

DEFAULT_USER_ID: Optional[int] = None


# ---- Helpers ----
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def isoformat(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def current_user_id() -> int:
    return DEFAULT_USER_ID or get_default_user_id()


def model_for_provider(provider: str) -> str:
    if provider.lower() == "openai":
        return DEFAULT_OPENAI_MODEL
    return DEFAULT_VLLM_MODEL


def serialize_attachment(a: Attachment) -> Dict:
    return {
        "id": a.id,
        "name": a.name,
        "type": a.type,
        "fileHash": a.file_hash,
        "createdAt": isoformat(a.created_at),
    }


def serialize_message(msg: Message) -> Dict:
    meta = msg.meta or {}
    return {
        "id": str(msg.id),
        "role": msg.role,
        "content": msg.content,
        "createdAt": isoformat(msg.created_at),
        "useDocs": bool(meta.get("use_docs", False)),
        "citations": meta.get("citations") or [],
        "evidence": meta.get("evidence") or [],
        "meta": {
            "answerMode": meta.get("answer_mode"),
            "verdict": meta.get("verdict"),
            "confidence": meta.get("confidence"),
            "warning": meta.get("warning"),
        },
    }


def serialize_conversation(conv: Conversation) -> Dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "createdAt": isoformat(conv.created_at),
        "lastUpdatedAt": isoformat(conv.updated_at),
        "isPinned": bool(conv.is_pinned),
        "pinnedAt": isoformat(conv.pinned_at),
        "pinnedOrder": conv.pinned_order,
    }


def chunk_text(text: str, size: int = 120) -> List[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def ensure_conversation(db: Session, conversation_id: int, user_id: int) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def count_attachments(db: Session, conversation_id: int, user_id: int) -> int:
    return (
        db.query(func.count(Attachment.id))
        .filter(
            Attachment.conversation_id == conversation_id,
            Attachment.user_id == user_id,
        )
        .scalar()
    )


def build_chat_history(db: Session, conversation_id: int) -> List[Dict]:
    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    trimmed = history[-MAX_TURNS:]
    return [{"role": m.role, "content": m.content} for m in trimmed]


def enforce_use_docs(
    db: Session, conversation_id: int, user_id: int, requested: bool
) -> tuple[bool, Optional[str]]:
    attachments_count = count_attachments(db, conversation_id, user_id)
    if attachments_count == 0:
        return False, "useDocs disabled because the conversation has no attachments."
    return requested, None


def build_citations(evidence_hits: List[Dict], verdict: Optional[str]) -> List[Dict]:
    if verdict == "UNSUPPORTED":
        return []
    citations: List[Dict] = []
    for h in evidence_hits:
        att_id = h.get("attachment_id")
        if not att_id:
            continue
        citations.append(
            {
                "attachmentId": att_id,
                "page": h.get("page"),
            }
        )
    return citations


def build_evidence(evidence_hits: List[Dict], verdict: Optional[str]) -> List[Dict]:
    if verdict == "UNSUPPORTED":
        return []
    evidence: List[Dict] = []
    for idx, h in enumerate(evidence_hits, start=1):
        att_id = h.get("attachment_id")
        if not att_id:
            continue
        evidence.append(
            {
                "attachmentId": att_id,
                "page": h.get("page"),
                "excerpt": h.get("excerpt"),
                "filename": h.get("filename"),
                "rank": idx,
            }
        )
    return evidence


def save_routing_decision(
    db: Session,
    message_id: int,
    answer_mode: str,
    reason: str,
    confidence: float,
):
    decision = RoutingDecision(
        message_id=message_id,
        answer_mode=answer_mode,
        reason=reason,
        confidence=confidence,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)


def add_message(
    db: Session,
    conversation: Conversation,
    role: str,
    content: str,
    meta: Optional[Dict] = None,
) -> Message:
    conversation.updated_at = datetime.utcnow()
    msg = Message(
        conversation_id=conversation.id,
        role=role,
        content=content,
        meta=meta if meta is not None else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(conversation)
    db.refresh(msg)
    return msg


def generate_answer(
    *,
    db: Session,
    conversation: Conversation,
    user_message: str,
    use_docs_requested: bool,
) -> tuple[str, Dict, str]:
    """
    Generate an assistant response and return (final_text, meta, routing_reason).
    """
    user_id = conversation.user_id
    use_docs, warning = enforce_use_docs(db, conversation.id, user_id, use_docs_requested)

    provider = DEFAULT_PROVIDER
    model = model_for_provider(provider)
    chat_client = get_chat_client(provider)
    chat_history = build_chat_history(db, conversation.id)

    if not use_docs:
        system_prompt = (
            "You are a helpful assistant. Answer concisely and accurately.\n"
            "If the question requires document-specific facts, mention that no documents are available."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            *chat_history,
            {"role": "user", "content": user_message},
        ]
        resp = chat_client.chat_complete(
            model=model,
            messages=messages,
            stream=False,
        )
        answer = resp.choices[0].message.content or ""
        meta = {
            "use_docs": False,
            "citations": [],
            "evidence": [],
            "answer_mode": "direct",
            "verdict": None,
            "confidence": None,
            "warning": warning,
        }
        routing_reason = warning or "Answered without document retrieval."
        return answer, meta, routing_reason

    # ---- RAG path ----
    intent = classify_intent(user_message)
    preferred = preferred_sections(intent)
    hard_sections = preferred if should_hard_filter(intent) and preferred else None

    hits = retrieve_hits(
        user_message,
        user_id=user_id,
        conversation_id=conversation.id,
        k=30,
        intent=intent,
        hard_sections=hard_sections,
        preferred=preferred,
    )

    hits = rerank(user_message, hits, top_n=18)
    context, sources, evidence_hits = build_context_and_sources(hits, top_pages=3)

    answer_system = (
        "You are a helpful assistant answering questions using the provided document excerpts.\n"
        "Write one clear paragraph grounded in the excerpts.\n"
        "If no relevant excerpts exist, say you cannot find a supported answer in the provided documents.\n\n"
        f"DOCUMENT EXCERPTS:\n{context}"
        if context
        else "You are a helpful assistant. No document excerpts were provided."
    )
    answer_messages = [
        {"role": "system", "content": answer_system},
        *chat_history,
        {"role": "user", "content": user_message},
    ]

    resp = chat_client.chat_complete(
        model=model,
        messages=answer_messages,
        stream=False,
    )
    draft = resp.choices[0].message.content or ""

    final_answer, vdebug = verify_answer(
        chat_client=chat_client,
        model=model,
        question=user_message,
        draft=draft,
        context=context,
        evidence_hits=evidence_hits,
        refusal_text="I can’t find a supported answer in the provided document excerpts.",
    )
    verdict = (vdebug or {}).get("verdict", "UNSUPPORTED")
    confidence = (vdebug or {}).get("confidence", 0.0)
    if context and verdict == "UNSUPPORTED":
        verdict = "PARTIAL"
        final_answer = draft
        confidence = min(float(confidence or 0.0), 0.55)

    citations = build_citations(evidence_hits, verdict)
    evidence = build_evidence(evidence_hits, verdict)
    meta = {
        "use_docs": True,
        "citations": citations,
        "evidence": evidence,
        "answer_mode": "rag",
        "verdict": verdict,
        "confidence": confidence,
        "warning": warning,
        "sources": sources,
    }
    routing_reason = "RAG enabled with document retrieval."
    return final_answer, meta, routing_reason


def ensure_pinned_capacity(db: Session, user_id: int, exclude_id: Optional[int] = None):
    q = db.query(func.count(Conversation.id)).filter(
        Conversation.user_id == user_id,
        Conversation.is_pinned.is_(True),
    )
    if exclude_id:
        q = q.filter(Conversation.id != exclude_id)
    if q.scalar() >= MAX_PINNED:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_PINNED} pinned conversations reached.",
        )


def assign_pinned_order(db: Session, user_id: int) -> int:
    current_max = (
        db.query(func.max(Conversation.pinned_order))
        .filter(
            Conversation.user_id == user_id,
            Conversation.is_pinned.is_(True),
            Conversation.pinned_order.isnot(None),
        )
        .scalar()
    )
    return (current_max or 0) + 1


# ---- Startup ----
@app.on_event("startup")
def on_startup():
    global DEFAULT_USER_ID
    DEFAULT_USER_ID = init_db()


# ---- Routes ----
@app.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    user_id = current_user_id()
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(
            Conversation.is_pinned.desc(),
            Conversation.pinned_order.asc().nullslast(),
            Conversation.pinned_at.desc().nullslast(),
            Conversation.updated_at.desc().nullslast(),
        )
        .all()
    )
    return [serialize_conversation(c) for c in convs]


@app.post("/conversations")
def create_conversation(db: Session = Depends(get_db)):
    user_id = current_user_id()
    title = f"Session {datetime.utcnow().isoformat(timespec='minutes')}"

    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    use_docs_default = True if settings is None else bool(settings.use_docs_default)

    conv = Conversation(
        user_id=user_id,
        title=title,
        use_docs_default=use_docs_default,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return serialize_conversation(conv)


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    user_id = current_user_id()
    conv = ensure_conversation(db, conversation_id, user_id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at)
        .all()
    )
    attachments = (
        db.query(Attachment)
        .filter(
            Attachment.conversation_id == conv.id,
            Attachment.user_id == user_id,
        )
        .order_by(Attachment.created_at.desc())
        .all()
    )
    return {
        "conversation": serialize_conversation(conv),
        "messages": [serialize_message(m) for m in messages],
        "attachments": [serialize_attachment(a) for a in attachments],
    }


@app.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: int,
    payload: Dict = Body(...),
    db: Session = Depends(get_db),
):
    user_id = current_user_id()
    conv = ensure_conversation(db, conversation_id, user_id)

    title = payload.get("title")
    is_pinned = payload.get("isPinned")

    if title is not None:
        conv.title = title.strip() or conv.title
        conv.updated_at = datetime.utcnow()

    if is_pinned is not None:
        if is_pinned:
            ensure_pinned_capacity(db, user_id, exclude_id=conv.id)
            conv.is_pinned = True
            conv.pinned_at = datetime.utcnow()
            if conv.pinned_order is None:
                conv.pinned_order = assign_pinned_order(db, user_id)
        else:
            conv.is_pinned = False
            conv.pinned_at = None
            conv.pinned_order = None
        conv.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(conv)
    return serialize_conversation(conv)


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    user_id = current_user_id()
    conv = ensure_conversation(db, conversation_id, user_id)

    # Capture attachment paths for cleanup before deleting ORM objects
    attachment_paths = [a.path for a in conv.attachments if a.path]

    db.delete(conv)
    db.commit()

    delete_conversation_embeddings(conversation_id, user_id)

    for path in attachment_paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    conv_dir = os.path.join(RAW_DATA_DIR, str(user_id), str(conversation_id))
    if os.path.isdir(conv_dir):
        try:
            os.rmdir(conv_dir)
        except OSError:
            # Directory may not be empty; leave it.
            pass

    return {"status": "deleted"}


@app.put("/conversations/pinned-order")
def update_pinned_order(payload: Dict = Body(...), db: Session = Depends(get_db)):
    user_id = current_user_id()
    order = payload.get("ids") or payload.get("conversationIds")
    if not isinstance(order, list):
        raise HTTPException(status_code=400, detail="Body must include ordered list of pinned conversation IDs.")

    pinned_convs = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user_id,
            Conversation.id.in_(order),
        )
        .all()
    )
    pinned_map = {c.id: c for c in pinned_convs}
    missing = [cid for cid in order if cid not in pinned_map]
    if missing:
        raise HTTPException(status_code=400, detail=f"Invalid conversation ids: {missing}")

    for idx, cid in enumerate(order, start=1):
        conv = pinned_map[cid]
        conv.is_pinned = True
        conv.pinned_order = idx
        if not conv.pinned_at:
            conv.pinned_at = datetime.utcnow()
        conv.updated_at = datetime.utcnow()

    db.commit()
    return {"status": "ok"}


@app.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, db: Session = Depends(get_db)):
    user_id = current_user_id()
    ensure_conversation(db, conversation_id, user_id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    return [serialize_message(m) for m in messages]


@app.post("/conversations/{conversation_id}/messages")
def create_message(
    conversation_id: int,
    payload: Dict = Body(...),
    db: Session = Depends(get_db),
):
    user_id = current_user_id()
    conv = ensure_conversation(db, conversation_id, user_id)
    content = (payload.get("content") or "").strip()
    use_docs = bool(payload.get("useDocs", conv.use_docs_default))
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required.")

    user_msg = add_message(db, conv, "user", content)

    try:
        answer, meta, reason = generate_answer(
            db=db,
            conversation=conv,
            user_message=content,
            use_docs_requested=use_docs,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    assistant_msg = add_message(db, conv, "assistant", answer, meta=meta)
    save_routing_decision(
        db=db,
        message_id=assistant_msg.id,
        answer_mode=meta.get("answer_mode", "direct"),
        reason=reason,
        confidence=meta.get("confidence") or 1.0,
    )

    warning = meta.get("warning")
    response = {
        "messages": [serialize_message(user_msg), serialize_message(assistant_msg)],
    }
    if warning:
        response["warning"] = warning
    return response


@app.post("/conversations/{conversation_id}/messages:stream")
async def stream_message(
    conversation_id: int,
    payload: Dict = Body(...),
    db: Session = Depends(get_db),
):
    user_id = current_user_id()
    conv = ensure_conversation(db, conversation_id, user_id)
    content = (payload.get("content") or "").strip()
    use_docs = bool(payload.get("useDocs", conv.use_docs_default))
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required.")

    user_msg = add_message(db, conv, "user", content)

    def event_builder():
        try:
            yield f"event: message.status\ndata: {json.dumps({'status': 'thinking'})}\n\n"
            answer, meta, reason = generate_answer(
                db=db,
                conversation=conv,
                user_message=content,
                use_docs_requested=use_docs,
            )
            assistant_msg = add_message(db, conv, "assistant", answer, meta=meta)
            save_routing_decision(
                db=db,
                message_id=assistant_msg.id,
                answer_mode=meta.get("answer_mode", "direct"),
                reason=reason,
                confidence=meta.get("confidence") or 1.0,
            )

            for delta in chunk_text(answer):
                yield f"event: message.delta\ndata: {json.dumps({'delta': delta})}\n\n"

            final_payload = serialize_message(assistant_msg)
            warning = meta.get("warning")
            if warning:
                final_payload["warning"] = warning
            yield f"event: message.final\ndata: {json.dumps(final_payload)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_builder(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/conversations/{conversation_id}/attachments")
def list_attachments(conversation_id: int, db: Session = Depends(get_db)):
    user_id = current_user_id()
    ensure_conversation(db, conversation_id, user_id)
    attachments = (
        db.query(Attachment)
        .filter(
            Attachment.conversation_id == conversation_id,
            Attachment.user_id == user_id,
        )
        .order_by(Attachment.created_at.desc())
        .all()
    )
    return [serialize_attachment(a) for a in attachments]


@app.post("/conversations/{conversation_id}/attachments")
async def upload_attachment(
    conversation_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user_id = current_user_id()
    conv = ensure_conversation(db, conversation_id, user_id)

    existing = count_attachments(db, conversation_id, user_id)
    data = await file.read()
    file_hash = hashlib.sha256(data).hexdigest()

    existing_hash = (
        db.query(Attachment)
        .filter(
            Attachment.conversation_id == conversation_id,
            Attachment.user_id == user_id,
            Attachment.file_hash == file_hash,
        )
        .first()
    )

    if not existing_hash and existing >= MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_ATTACHMENTS} attachments per conversation.",
        )

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in SUPPORTED_ATTACHMENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    conv_dir = os.path.join(RAW_DATA_DIR, str(user_id), str(conversation_id))
    os.makedirs(conv_dir, exist_ok=True)

    safe_name = os.path.basename(file.filename)
    path = os.path.join(conv_dir, safe_name)
    with open(path, "wb") as f:
        f.write(data)

    ingest_file(
        path,
        conversation_id=conversation_id,
        user_id=user_id,
        mime_type=file.content_type,
        attachment_type=ext,
    )

    # Ensure the ORM row has the latest path + type
    attachment = (
        db.query(Attachment)
        .filter(
            Attachment.conversation_id == conversation_id,
            Attachment.user_id == user_id,
            Attachment.file_hash == file_hash,
        )
        .order_by(Attachment.created_at.desc())
        .first()
    )
    if attachment:
        attachment.path = path
        attachment.type = ext
        conv.updated_at = datetime.utcnow()
        if not conv.use_docs_default:
            conv.use_docs_default = True
        db.commit()
        db.refresh(attachment)
        db.refresh(conv)
    else:
        raise HTTPException(status_code=500, detail="Failed to persist attachment.")

    return serialize_attachment(attachment)


@app.get("/attachments/{attachment_id}/content")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    user_id = current_user_id()
    attachment = (
        db.query(Attachment)
        .filter(
            Attachment.id == attachment_id,
            Attachment.user_id == user_id,
        )
        .first()
    )
    if not attachment or not attachment.path:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    if not os.path.exists(attachment.path):
        raise HTTPException(status_code=404, detail="Attachment file missing on disk.")
    mime_map = {
        "pdf": "application/pdf",
        "txt": "text/plain; charset=utf-8",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    attachment_type = (attachment.type or "").lower()
    media_type = mime_map.get(attachment_type, "application/octet-stream")
    return FileResponse(
        attachment.path,
        filename=attachment.name,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{attachment.name}"'},
    )


@app.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    user_id = current_user_id()
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id, theme=None, use_docs_default=True)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return {
        "theme": settings.theme,
        "useDocs": bool(settings.use_docs_default),
    }


@app.patch("/settings")
def update_settings(payload: Dict = Body(...), db: Session = Depends(get_db)):
    user_id = current_user_id()
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id, theme=None, use_docs_default=True)
        db.add(settings)

    if "theme" in payload:
        settings.theme = payload.get("theme")
    if "useDocs" in payload:
        settings.use_docs_default = bool(payload.get("useDocs"))

    db.commit()
    db.refresh(settings)
    return {
        "theme": settings.theme,
        "useDocs": bool(settings.use_docs_default),
    }
