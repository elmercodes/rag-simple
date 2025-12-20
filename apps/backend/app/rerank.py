from typing import List, Dict
from sentence_transformers import CrossEncoder

# Small, fast reranker model
_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank(query: str, hits: List[Dict], top_n: int = 8) -> List[Dict]:
    pairs = [(query, h.get("raw_text", h["text"])) for h in hits]

    scores = _model.predict(pairs)

    for h, s in zip(hits, scores):
        h["rerank_score"] = float(s)

    hits.sort(key=lambda x: x["rerank_score"], reverse=True)
    return hits[:top_n]
