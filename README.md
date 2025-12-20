# RAG-simple

Chat with your uploaded documents using a retrieval-augmented generation pipeline that is biased toward grounded, citation-backed answers. This repo now exposes a FastAPI backend that the Next.js frontend will consume.

## Architecture (how it stays accurate)
- **Document ingestion** (`backend/app/vectorstore.py`): PDFs/TXTs/DOCXs are parsed into pages, chunked on paragraphs, and tagged with section hints (intro/how-to/reference/impact, etc.). Duplicate uploads are deduped by file hash. Chunk metadata is written to SQLite (`data/chat.db`) for observability and to a persistent Chroma collection (`data/vector_store`) for fast similarity search scoped per conversation + user.
- **Embeddings + store** (`backend/app/embeddings.py`, `vectorstore.py`): Uses `text-embedding-3-small` via OpenAI to embed chunks, stored with rich metadata (file, page, section, chunk id, preview). Queries are embedded the same way and searched with Chroma; results are always filtered to the active conversation to avoid cross-chat leakage.
- **Retrieval policy** (`backend/app/retrieval_policy.py`): Classifies intent (motivation/how-to/performance/impact/etc.) and gently boosts or filters sections so the retriever prefers the part of the doc that is most likely to contain the answer. When uncertain, it defaults to RAG to avoid hallucinations.
- **Rerank + page-first context** (`backend/app/rerank.py`, `vectorstore.py`): A cross-encoder (`ms-marco-MiniLM-L-6-v2`) reranks the top dense-retrieval hits. Chunks are then grouped by page; the best pages are chosen first, and only a few high-scoring chunks per page are sent to the model. This keeps context tight and prevents noisy, off-page tangents.
- **Answer generation + verification** (`backend/main.py`, `backend/app/verification.py`): The model writes a single paragraph from the selected evidence. A second pass judges whether the draft is supported by the excerpts; unsupported answers are replaced with a refusal, and citations are hidden when evidence is weak. This two-pass guard reduces hallucinations without over-refusing.
- **Routing + toggles** (`backend/main.py`): The API enforces `useDocs` based on attachments. All retrieval, rerank, and verification decisions are stored in the DB so you can audit what evidence produced a reply.

## Data flow
1) **Upload** files via `POST /conversations/{id}/attachments`. Files are saved under `data/raw/{user_id}/{conversation_id}/` and ingested.
2) **Ingest**: Files are chunked, embedded, deduped, and stored in Chroma; chunk metadata is mirrored to SQLite.
3) **Ask**: A query is embedded, policy-routed, retrieved, reranked, and narrowed to the best pages.
4) **Answer**: The model writes from the curated context; a verifier checks support before the response and evidence are returned to the frontend.

## Quick start (local)
- Set `OPENAI_API_KEY` in your environment (optionally `OPENAI_MODEL`, `LLM_PROVIDER`, `VLLM_BASE_URL`, `VLLM_API_KEY`).
- Install deps: `pip install -r requirements.txt`.
- Run the API: `uvicorn backend.main:app --reload`.
- Open the interactive docs at `http://localhost:8000/docs` to exercise the endpoints.
