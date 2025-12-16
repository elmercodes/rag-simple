import re
from typing import List, Dict, Tuple

from .embeddings import embed_texts

def _split_claims(text: str) -> List[str]:
    """
    Simple claim splitter:
    - splits bullets and sentences
    - removes tiny fragments
    """
    if not text:
        return []

    # normalize bullets
    text = text.replace("\r", "\n")
    parts = []

    # split by bullet lines first
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(("-", "*")):
            line = line.lstrip("-* ").strip()
        parts.append(line)

    # then split by sentence boundaries
    claims = []
    for p in parts:
        # naive sentence split
        for s in re.split(r"(?<=[.!?])\s+", p):
            s = s.strip()
            if len(s) >= 25:  # filter tiny fragments
                claims.append(s)

    # de-duplicate
    seen = set()
    out = []
    for c in claims:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _cosine(a: List[float], b: List[float]) -> float:
    # safe cosine; assumes embeddings are non-zero
    import math
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def verify_answer(
    answer_text: str,
    evidence_hits: List[Dict],
    support_threshold: float = 0.78,
    weak_threshold: float = 0.70,
    max_snippet_chars: int = 220,
) -> Tuple[str, Dict]:
    """
    Verifies answer claims against evidence_hits (ONLY the hits you used to build context).
    Returns (verified_answer, debug_info)

    evidence_hits must contain:
      - "text" (chunk)
    """
    claims = _split_claims(answer_text)
    if not claims or not evidence_hits:
        return answer_text, {"claims": [], "kept": 0, "dropped": 0}

    # Embed evidence chunks once
    evidence_texts = [h.get("raw_text", h["text"]) for h in evidence_hits]
    evidence_vecs = embed_texts(evidence_texts)

    kept = []
    debug_claims = []

    # Embed claims in a batch
    claim_vecs = embed_texts(claims)

    for claim, cvec in zip(claims, claim_vecs):
        best_i = -1
        best_sim = -1.0

        for i, evec in enumerate(evidence_vecs):
            sim = _cosine(cvec, evec)
            if sim > best_sim:
                best_sim = sim
                best_i = i

        if best_i >= 0:
            best_hit = evidence_hits[best_i]
            snippet = best_hit["text"].strip().replace("\n", " ")
            snippet = snippet[:max_snippet_chars] + ("..." if len(snippet) > max_snippet_chars else "")

            if best_sim >= support_threshold:
                kept.append(claim)
                status = "supported"
            elif best_sim >= weak_threshold:
                # keep but hedge
                kept.append(f"(Possibly) {claim}")
                status = "weak"
            else:
                status = "unsupported"

            debug_claims.append({
                "claim": claim,
                "status": status,
                "similarity": float(best_sim),
                "best_page": best_hit.get("page"),
                "best_file": best_hit.get("filename"),
                "snippet": snippet,
            })

    if not kept:
        # hard refuse if nothing is grounded
        verified = "I can’t find a supported answer in the provided document excerpts."
    else:
        verified = "\n".join(f"- {k}" for k in kept)

    debug = {
        "claims": debug_claims,
        "kept": len(kept),
        "dropped": len([c for c in debug_claims if c["status"] == "unsupported"]),
    }
    return verified, debug
