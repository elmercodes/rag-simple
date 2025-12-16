# backend/app/vectorstore.py
import os
import uuid
from typing import List, Dict, Tuple
from collections import defaultdict
import re

import chromadb
from pypdf import PdfReader

from .embeddings import embed_texts
from .sectioning import detect_section_from_page_text


# --------------------------------------------------------------------
# PATHS & CLIENT
# --------------------------------------------------------------------

# project root: backend/app -> backend -> project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
VECTOR_DIR = os.path.join(BASE_DIR, "data", "vector_store")

os.makedirs(VECTOR_DIR, exist_ok=True)

# For now, keep it simple: one persistent Chroma client + collection
_client = chromadb.PersistentClient(path=VECTOR_DIR)
_collection = _client.get_or_create_collection("docs")


# --------------------------------------------------------------------
# CHUNKING
# --------------------------------------------------------------------

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



# --------------------------------------------------------------------
# INGESTION
# --------------------------------------------------------------------

def ingest_pdf(path: str) -> str:
    """
    Read a PDF, chunk it, embed, and store in Chroma.

    Returns:
        doc_id (str): UUID for this document.
    """
    doc_id = str(uuid.uuid4())
    filename = os.path.basename(path)

    reader = PdfReader(path)

    ids = []
    docs = []
    metas = []

    current_section = "other"

    for page_idx, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        current_section = detect_section_from_page_text(
            page_text,
            current_section=current_section,
            enable_paper_patterns=True,  # works for papers + general docs
        )

        chunks = _chunk_text(page_text)
        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            ids.append(chunk_id)

            docs.append(chunk)

            # ---- NEW: better metadata ----
            preview = chunk.strip().replace("\n", " ")
            preview = preview[:200] + ("..." if len(preview) > 200 else "")

            metas.append(
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": page_idx,
                    "chunk_index": i,
                    "section": current_section,
                    "char_len": len(chunk),
                    "preview": preview,
                }
            )


    # No text? Still return doc_id so caller knows we "handled" it.
    if not docs:
        return doc_id

    vectors = embed_texts(docs)

    _collection.add(
        ids=ids,
        documents=docs,
        embeddings=vectors,
        metadatas=metas,
    )

    return doc_id


# --------------------------------------------------------------------
# RETRIEVAL (RAG)
# --------------------------------------------------------------------

def retrieve_context_and_sources(
    query: str,
    k: int = 8,
    top_pages: int = 2,
) -> Tuple[str, List[Dict]]:
    """
    Given a query string, return:

    - context: concatenated top-k chunk texts
    - sources: list of top 'page' hits with filename + page number
    """
    q_vec = embed_texts([query])[0]

    res = _collection.query(
        query_embeddings=[q_vec],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    if not res["documents"] or not res["documents"][0]:
        return "", []

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]

    # Convert distances (smaller = better) to scores
    scores = [1 / (1 + d) for d in dists]

    # Aggregate scores by (doc_id, filename, page)
    page_scores = defaultdict(float)
    for meta, score in zip(metas, scores):
        key = (meta["doc_id"], meta["filename"], meta["page"])
        page_scores[key] += score

    best_pages = sorted(
        page_scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:top_pages]

    sources = [
        {"doc_id": k[0][0], "filename": k[0][1], "page": k[0][2]}
        for k in best_pages
    ]

    # Build context as concatenation of retrieved chunks
    context = "\n\n---\n\n".join(docs)

    return context, sources

def retrieve_hits(
    query: str,
    k: int = 30,
    intent: str = "general",
    hard_sections: list[str] | None = None,
    preferred: list[str] | None = None,
) -> List[Dict]:
    q_vec = embed_texts([query])[0]

    # --- OPTIONAL HARD FILTER BY SECTION ---
    where = None
    if hard_sections:
        where = {"section": {"$in": hard_sections}}

    res = _collection.query(
        query_embeddings=[q_vec],
        n_results=k,
        include=["documents", "metadatas", "distances"],
        where=where,  # <-- this is the key change
    )

    if not res["documents"] or not res["documents"][0]:
        return []

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        section = meta.get("section", "other")

        # Base score from vector similarity
        score = 1 / (1 + dist)

        # --- RULE 2: DISCOUNT IMPACT SECTION FOR TECHNICAL CLAIMS ---
        # (generalized "Broader Impact" rule)
        if intent != "impact" and section == "impact":
            score *= 0.35

        # --- RULE 1/3: EVIDENCE-TYPE MATCHING (SOFT BOOST/PENALTY) ---
        if preferred:
            if section in preferred:
                score *= 1.25
            else:
                score *= 0.90

        excerpt = doc.strip().replace("\n", " ")
        excerpt = excerpt[:300] + ("..." if len(excerpt) > 300 else "")

        raw = doc  # doc is now raw chunk text

        display_text = f"Document: {meta.get('filename')}\nPage: {meta.get('page')}\n\n{raw}"

        excerpt = raw.strip().replace("\n", " ")
        excerpt = excerpt[:300] + ("..." if len(excerpt) > 300 else "")

        hits.append({
            "score": score,
            "raw_text": raw,          # ✅ for rerank/verify
            "text": display_text,     # ✅ for context shown to LLM (optional)
            "excerpt": excerpt,       # ✅ for UI
            "filename": meta.get("filename"),
            "page": meta.get("page"),
            "doc_id": meta.get("doc_id"),
            "chunk_index": meta.get("chunk_index"),
            "section": section,
        })


    hits.sort(key=lambda h: h["score"], reverse=True)

    return hits



def build_context_and_sources(
    hits: List[Dict],
    top_pages: int = 2,
    chunks_per_page: int = 4,
) -> Tuple[str, List[Dict]]:
    """
    Page-first selection using rerank_score when present.
    Then build context ONLY from chunks on selected pages.
    """

    if not hits:
        return "", []

    # Use rerank_score if available, else fall back to score
    def s(h: Dict) -> float:
        return float(h.get("rerank_score", h.get("score", 0.0)))

    # 1) Aggregate score by (doc_id, filename, page)
    page_scores = defaultdict(float)
    page_to_hits = defaultdict(list)

    for h in hits:
        key = (h["doc_id"], h["filename"], h["page"])
        page_scores[key] += s(h)
        page_to_hits[key].append(h)

    # 2) Pick top pages
    best_pages = sorted(page_scores.items(), key=lambda x: x[1], reverse=True)[:top_pages]
    selected_page_keys = [k for (k, _) in best_pages]

    sources = [{"doc_id": k[0], "filename": k[1], "page": k[2]} for k in selected_page_keys]

    # 3) Build context: only from selected pages, best chunks first
    selected_hits = []
    for k in selected_page_keys:
        page_hits = sorted(page_to_hits[k], key=s, reverse=True)[:chunks_per_page]
        selected_hits.extend(page_hits)

    # Keep overall ordering by score
    selected_hits.sort(key=s, reverse=True)

    context = "\n\n---\n\n".join([h["text"] for h in selected_hits])
    return context, sources, selected_hits

