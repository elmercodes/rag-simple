import os
import uuid
import re
import hashlib
from collections import defaultdict
from typing import Tuple, List, Dict

import chromadb
from pypdf import PdfReader
from docx import Document as DocxDocument

from .embeddings import (
    embed_texts,
    embed_query,
    embedding_dimension,
)
from .sectioning import detect_section_from_page_text
from .db import SessionLocal
from .models import Attachment as AttachmentModel, AttachmentChunk


# -------------------- Paths & Client --------------------

# project root: backend/app -> backend -> project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
VECTOR_DIR = os.path.join(BASE_DIR, "data", "vector_store")

os.makedirs(VECTOR_DIR, exist_ok=True)

# For now, keep it simple: one persistent Chroma client + named collections
_client = chromadb.PersistentClient(path=VECTOR_DIR)
_collections: Dict[str, chromadb.api.models.Collection.Collection] = {}

# Legacy (OpenAI) + new BGE collection names
LEGACY_COLLECTION_NAME = "docs"  # existing collection with OpenAI embeddings
BGE_COLLECTION_NAME = "chroma_bge_large_en_v1_5"


def _get_collection(name: str):
    if name not in _collections:
        _collections[name] = _client.get_or_create_collection(name)
    return _collections[name]


def _db_session():
    return SessionLocal()


def _embedding_config_for_model(embedding_model: str) -> Dict:
    if embedding_model == "openai-embeddings":
        return {
            "embedding_model": embedding_model,
            "embedding_dim": embedding_dimension(embedding_model),
            "vectorstore_collection": LEGACY_COLLECTION_NAME,
        }
    if embedding_model == "bge-large-en-v1.5":
        return {
            "embedding_model": embedding_model,
            "embedding_dim": embedding_dimension(embedding_model),
            "vectorstore_collection": BGE_COLLECTION_NAME,
        }
    raise ValueError(f"Unsupported embedding model: {embedding_model}")


def _collection_for_config(cfg: Dict):
    return _get_collection(cfg["vectorstore_collection"])


def _scoped_where(conversation_id: int, user_id: int, extra: Dict | None = None) -> Dict:
    """
    Build a Chroma where clause that always scopes to conversation + user.
    Chroma expects a single top-level operator, so we use $and.
    """
    clauses = [
        {"conversation_id": conversation_id},
        {"user_id": user_id},
    ]
    if extra:
        clauses.append(extra)
    return {"$and": clauses}


# -------------------- Helpers --------------------

def _file_sha256(path: str, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_doc_id(path: str) -> str:
    """
    Stable doc_id so re-uploading same exact file doesn't create duplicates.
    Uses SHA256(file bytes). Not a UUID.
    """
    return _file_sha256(path)


def _delete_existing_doc(
    doc_id: str,
    conversation_id: int,
    user_id: int,
    collection,
) -> None:
    """
    Remove existing chunks for this doc_id so re-ingesting updates cleanly.
    Scoped by conversation/user to avoid cross-chat deletions.
    """
    try:
        existing = collection.get(
            where=_scoped_where(
                conversation_id,
                user_id,
                extra={"doc_id": doc_id},
            )
        )
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
    except Exception:
        # If collection.get(where=...) isn't supported by your Chroma version,
        # we can swap to a query-based delete later. For now, fail-soft.
        pass


def _page_key(doc_id: str, filename: str, page: int) -> Tuple[str, str, int]:
    """Consistent page key used for aggregation/deduping."""
    return (doc_id, filename, page)


def _embed_query(query: str, cfg: Dict) -> List[float]:
    """Embed a single query using the embedding model tied to the collection."""
    return embed_query(query, cfg["embedding_model"])


def _similarity_from_distance(distance: float) -> float:
    return 1 / (1 + distance)


def _extract_query_rows(res) -> List[Tuple[str, Dict, float]]:
    """
    Normalize Chroma query response into a list of (doc, meta, distance) tuples.
    Keeps ordering identical to the underlying response.
    """
    if not res["documents"] or not res["documents"][0]:
        return []

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    return list(zip(docs, metas, dists))


# -------------------- File Reading --------------------

def _read_pdf_pages(path: str) -> List[Tuple[int, str]]:
    reader = PdfReader(path)
    pages = []
    for page_idx, page in enumerate(reader.pages, start=1):
        pages.append((page_idx, page.extract_text() or ""))
    return pages


def _read_txt_pages(path: str) -> List[Tuple[int, str]]:
    # Treat as single "page" for now
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return [(1, text)]


def _read_docx_pages(path: str) -> List[Tuple[int, str]]:
    # DOCX doesn't have true pages easily without layout engine.
    # Treat as one "page" and rely on chunking.
    doc = DocxDocument(path)
    paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    text = "\n".join(paras)
    return [(1, text)]


def _read_any_file(path: str) -> List[Tuple[int, str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _read_pdf_pages(path)
    if ext == ".txt":
        return _read_txt_pages(path)
    if ext == ".docx":
        return _read_docx_pages(path)
    raise ValueError(f"Unsupported file type: {ext}")


# -------------------- Chunking --------------------

def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 0) -> List[str]:
    """
    Paragraph-aware chunking:
    - split into paragraphs
    - pack paragraphs into ~chunk_size chunks
    - add overlap (last overlap chars) between chunks
    """
    text = (text or "").strip()
    if not text:
        return []

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks = []
    buf = ""

    for p in paragraphs:
        if len(buf) + len(p) + 2 <= chunk_size:
            buf = (buf + "\n\n" + p).strip() if buf else p
        else:
            if buf:
                chunks.append(buf)
            buf = p

    if buf:
        chunks.append(buf)

    # Add overlap by prefixing each chunk with tail of previous chunk
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            tail = prev[-overlap:]
            overlapped.append((tail + "\n\n" + chunks[i]).strip())
        chunks = overlapped

    return chunks

# -------------------- Ingestion --------------------

def ingest_file(
    path: str,
    conversation_id: int,
    user_id: int,
    embedding_model: str,
    mime_type: str | None = None,
    attachment_type: str | None = None,
) -> str:
    """
    Read a file (PDF/TXT/DOCX), chunk it, embed it, and store in Chroma.

    - Uses a stable doc_id based on file content hash to prevent duplicates.
    - Deletes prior chunks for that doc_id before re-adding (update behavior).

    Returns:
        doc_id (str): stable id for this document.
    """
    doc_id = _stable_doc_id(path)
    filename = os.path.basename(path)
    if not attachment_type:
        ext = os.path.splitext(filename)[1].lower()
        if ext.startswith("."):
            ext = ext[1:]
        attachment_type = ext or mime_type
    embedding_cfg = _embedding_config_for_model(embedding_model)
    collection = _collection_for_config(embedding_cfg)

    # Remove previously ingested chunks for this doc (so re-upload updates)
    _delete_existing_doc(doc_id, conversation_id, user_id, collection)

    with _db_session() as db:
        attachment = (
            db.query(AttachmentModel)
            .filter(
                AttachmentModel.conversation_id == conversation_id,
                AttachmentModel.file_hash == doc_id,
            )
            .first()
        )

        if not attachment:
            attachment = AttachmentModel(
                user_id=user_id,
                conversation_id=conversation_id,
                name=filename,
                type=attachment_type or mime_type,
                path=path,
                file_hash=doc_id,
                embedding_model=embedding_cfg["embedding_model"],
                embedding_dim=embedding_cfg["embedding_dim"],
                vectorstore_collection=embedding_cfg["vectorstore_collection"],
            )
            db.add(attachment)
            db.commit()
            db.refresh(attachment)
        else:
            attachment.name = filename
            attachment.type = attachment_type or mime_type
            attachment.path = path
            attachment.embedding_model = embedding_cfg["embedding_model"]
            attachment.embedding_dim = embedding_cfg["embedding_dim"]
            attachment.vectorstore_collection = embedding_cfg["vectorstore_collection"]
            # Keep attachment row, but refresh chunks on re-upload/update.
            db.query(AttachmentChunk).filter(
                AttachmentChunk.attachment_id == attachment.id
            ).delete()
            db.commit()

        attachment_db_id = attachment.id

    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict] = []
    chunk_rows: List[AttachmentChunk] = []

    current_section = "other"

    # Read as list of (page_number, text)
    pages = _read_any_file(path)

    for page_idx, page_text in pages:
        page_text = page_text or ""

        # Optional section detection (works best for papers; for txt/docx usually stays "other")
        current_section = detect_section_from_page_text(
            page_text,
            current_section=current_section,
            enable_paper_patterns=True,
        )

        chunks = _chunk_text(page_text)
        for i, chunk in enumerate(chunks):
            if not chunk or not chunk.strip():
                continue

            chunk_id = str(uuid.uuid4())
            ids.append(chunk_id)
            docs.append(chunk)

            preview = chunk.strip().replace("\n", " ")
            preview = preview[:200] + ("..." if len(preview) > 200 else "")

            chunk_meta = {
                "doc_id": doc_id,
                "filename": filename,
                "page": page_idx,          # pdf: real page; txt/docx: 1
                "chunk_index": i,
                "section": current_section,
                "char_len": len(chunk),
                "preview": preview,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "attachment_id": attachment_db_id,
                "chunk_id": chunk_id,
                "embedding_model": embedding_cfg["embedding_model"],
                "embedding_dim": embedding_cfg["embedding_dim"],
                "vectorstore_collection": embedding_cfg["vectorstore_collection"],
            }

            metas.append(chunk_meta)

            chunk_rows.append(
                AttachmentChunk(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    attachment_id=attachment_db_id,
                    chunk_id=chunk_id,
                    chunk_text=chunk,
                    page=page_idx,
                    chunk_index=i,
                    section=current_section,
                    preview=preview,
                    char_len=len(chunk),
                    embedding_model=embedding_cfg["embedding_model"],
                    embedding_dim=embedding_cfg["embedding_dim"],
                    vectorstore_collection=embedding_cfg["vectorstore_collection"],
                )
            )

    # No text? Still return doc_id so caller knows we handled it.
    if not docs:
        return doc_id

    vectors = embed_texts(docs, embedding_model)

    collection.add(
        ids=ids,
        documents=docs,
        embeddings=vectors,
        metadatas=metas,
    )

    with _db_session() as db:
        # Fast insert of chunk metadata so UI/debug tooling can use it later.
        db.add_all(chunk_rows)
        db.commit()

    return doc_id

# -------------------- Retrieval (RAG) --------------------

def retrieve_context_and_sources(
    query: str,
    user_id: int,
    conversation_id: int,
    embedding_model: str,
    k: int = 8,
    top_pages: int = 2,
) -> Tuple[str, List[Dict]]:
    """
    Given a query string, return:

    - context: concatenated top-k chunk texts
    - sources: list of top 'page' hits with filename + page number
    """
    embedding_cfg = _embedding_config_for_model(embedding_model)
    collection = _collection_for_config(embedding_cfg)
    q_vec = _embed_query(query, embedding_cfg)

    # ---- Retrieval scoping ----
    res = collection.query(
        query_embeddings=[q_vec],
        n_results=k,
        include=["documents", "metadatas", "distances"],
        where=_scoped_where(conversation_id, user_id),
    )

    rows = _extract_query_rows(res)
    if not rows:
        return "", []

    scores = [_similarity_from_distance(dist) for _, _, dist in rows]

    # Aggregate scores by (doc_id, filename, page)
    page_scores = defaultdict(float)
    for (_, meta, _), score in zip(rows, scores):
        key = _page_key(meta["doc_id"], meta["filename"], meta["page"])
        page_scores[key] += score

    best_pages = sorted(
        page_scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:top_pages]

    sources = [
        {"doc_id": doc_id, "filename": filename, "page": page}
        for (doc_id, filename, page), _ in best_pages
    ]

    # Build context as concatenation of retrieved chunks
    context = "\n\n---\n\n".join(doc for doc, _, _ in rows)

    return context, sources


def retrieve_hits(
    query: str,
    user_id: int,
    conversation_id: int,
    embedding_model: str,
    k: int = 30,
    intent: str = "general",
    hard_sections: list[str] | None = None,
    preferred: list[str] | None = None,
) -> List[Dict]:
    embedding_cfg = _embedding_config_for_model(embedding_model)
    collection = _collection_for_config(embedding_cfg)
    q_vec = _embed_query(query, embedding_cfg)

    # --- OPTIONAL HARD FILTER BY SECTION ---
    extra = None
    if hard_sections:
        extra = {"section": {"$in": hard_sections}}

    # ---- Retrieval scoping ----
    res = collection.query(
        query_embeddings=[q_vec],
        n_results=k,
        include=["documents", "metadatas", "distances"],
        where=_scoped_where(conversation_id, user_id, extra=extra),
    )

    rows = _extract_query_rows(res)
    if not rows:
        return []

    hits: List[Dict] = []

    for doc, meta, dist in rows:
        section = meta.get("section", "other")
        attachment_id = meta.get("attachment_id") or meta.get("document_id")

        # --- base similarity score ---
        score = _similarity_from_distance(dist)

        # --- discount impact sections unless intent is impact ---
        if intent != "impact" and section == "impact":
            score *= 0.35

        # --- soft preference boost / penalty ---
        if preferred:
            if section in preferred:
                score *= 1.25
            else:
                score *= 0.90

        raw = doc  # raw chunk text

        # Text passed to the LLM (grounded with metadata)
        display_text = (
            f"FILE: {meta.get('filename')}\n"
            f"PAGE: {meta.get('page')}\n"
            f"SECTION: {section}\n\n"
            f"{raw}"
        )

        # Short preview for UI
        excerpt = raw.strip().replace("\n", " ")
        excerpt = excerpt[:300] + ("..." if len(excerpt) > 300 else "")

        hits.append({
            "score": score,
            "raw_text": raw,          # for rerank + verification
            "text": display_text,     # for LLM context
            "excerpt": excerpt,       # for UI
            "filename": meta.get("filename"),
            "page": meta.get("page"),
            "doc_id": meta.get("doc_id"),
            "attachment_id": attachment_id,
            "chunk_index": meta.get("chunk_index"),
            "section": section,
        })

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


def build_context_and_sources(
    hits: List[Dict],
    top_pages: int = 2,
    chunks_per_page: int = 4,
) -> Tuple[str, List[Dict], List[Dict]]:
    """
    Page-first selection using rerank_score when present.
    Builds context ONLY from chunks on selected pages.
    Returns: (context, sources, selected_hits)
    """

    if not hits:
        return "", [], []

    # Prefer rerank_score when available
    def score_fn(h: Dict) -> float:
        return float(h.get("rerank_score", h.get("score", 0.0)))

    # 1) Aggregate scores by page
    page_scores = defaultdict(float)
    page_to_hits = defaultdict(list)

    for h in hits:
        key = _page_key(h["doc_id"], h["filename"], h["page"])
        page_scores[key] += score_fn(h)
        page_to_hits[key].append(h)

    # 2) Select top pages
    best_pages = sorted(
        page_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )[:top_pages]

    selected_page_keys = [k for (k, _) in best_pages]

    # --- DEDUPE page keys ---
    seen = set()
    deduped_page_keys = []
    for k in selected_page_keys:
        if k in seen:
            continue
        seen.add(k)
        deduped_page_keys.append(k)

    selected_page_keys = deduped_page_keys

    # 3) Build sources list
    sources = [
        {"doc_id": doc_id, "filename": filename, "page": page}
        for (doc_id, filename, page) in selected_page_keys
    ]

    # 4) Collect best chunks from selected pages
    selected_hits: List[Dict] = []
    for k in selected_page_keys:
        page_hits = sorted(
            page_to_hits[k],
            key=score_fn,
            reverse=True
        )[:chunks_per_page]
        selected_hits.extend(page_hits)

    # Keep overall order stable
    selected_hits.sort(key=score_fn, reverse=True)

    # 5) Build LLM context
    context = "\n\n---\n\n".join(h["text"] for h in selected_hits)

    return context, sources, selected_hits


def delete_conversation_embeddings(conversation_id: int, user_id: int) -> None:
    """
    Remove all vector entries for a conversation across known collections.
    """
    collections = {BGE_COLLECTION_NAME, LEGACY_COLLECTION_NAME}
    for name in collections:
        collection = _get_collection(name)
        try:
            collection.delete(where=_scoped_where(conversation_id, user_id))
        except Exception:
            # Best-effort cleanup; ignore collection-specific failures.
            continue


def delete_attachment_embeddings(
    conversation_id: int,
    user_id: int,
    attachment_id: int,
) -> None:
    """
    Remove vector entries for a single attachment across known collections.
    """
    collections = {BGE_COLLECTION_NAME, LEGACY_COLLECTION_NAME}
    for name in collections:
        collection = _get_collection(name)
        try:
            collection.delete(
                where=_scoped_where(
                    conversation_id,
                    user_id,
                    extra={"attachment_id": attachment_id},
                )
            )
        except Exception:
            continue
