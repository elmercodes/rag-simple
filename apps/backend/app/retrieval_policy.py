import re
from typing import Dict, List, Optional, Sequence

def classify_intent(question: str) -> str:
    q = (question or "").lower()

    # Impact / ethics
    if any(k in q for k in ["ethic", "bias", "harm", "risk", "safety", "societ", "privacy", "security", "responsible"]):
        return "impact"

    # Troubleshooting
    if any(k in q for k in ["error", "exception", "failed", "doesn't work", "not working", "bug", "issue", "fix", "troubleshoot"]):
        return "troubleshooting"

    # Motivation / why
    if any(k in q for k in ["why", "motivation", "problem", "challenge", "goal", "purpose", "need", "limitations"]):
        return "motivation"

    # Definition / what is
    if re.match(r"^\s*(what is|define|definition of)\b", q) or "meaning of" in q:
        return "definition"

    # How-to / implementation
    if any(k in q for k in ["how do i", "how to", "steps", "setup", "install", "configure", "example", "implement"]):
        return "how_to"

    # Performance / quantitative / claims
    if any(k in q for k in ["accuracy", "f1", "auc", "benchmark", "results", "performance", "compare", "table", "figure", "latency", "throughput"]):
        return "performance"

    return "general"


def preferred_sections(intent: str) -> Optional[List[str]]:
    """
    Soft preference list (used for penalties/boosts).
    We only hard-filter when it’s safe; default is soft routing.
    """
    if intent == "motivation":
        return ["overview"]
    if intent == "definition":
        return ["reference", "overview"]
    if intent == "how_to":
        return ["how_to", "reference"]
    if intent == "performance":
        return ["reference"]
    if intent == "troubleshooting":
        return ["troubleshooting", "how_to", "reference"]
    if intent == "impact":
        return ["impact", "policies"]
    return None


def should_hard_filter(intent: str) -> bool:
    """
    Hard-filter only when missing the right section is unlikely.
    Motivation is safe to hard-filter to overview.
    Impact is safe to hard-filter to impact/policies.
    Everything else: soft preference.
    """
    return intent in {"motivation", "impact"}


# ------------------------------------------------------------------------------
# Routing: decide when to use RAG vs direct model answer
# ------------------------------------------------------------------------------

_OVERRIDE_RAG_PHRASES = [
    "use the document",
    "use the doc",
    "based on the document",
    "based on the pdf",
    "according to the pdf",
    "cite sources",
    "cite the sources",
    "include citations",
    "show citations",
    "from the pdf",
    "from the document",
    "in the document",
]

_OVERRIDE_DIRECT_PHRASES = [
    "answer generally",
    "don't use the document",
    "ignore the document",
    "no citations",
    "without the document",
]

_DOC_CUE_KEYWORDS = [
    "according to",
    "in the doc",
    "in the document",
    "in the pdf",
    "the pdf",
    "the document",
    "the file",
    "report",
    "paper",
    "section",
    "table",
    "figure",
    "page",
    "appendix",
    "cite",
    "citation",
    "sources",
    "page number",
]

_DOC_SUMMARY_KEYWORDS = [
    "summarize",
    "summary",
    "overview",
    "explain",
    "outline",
]

_GENERAL_CHAT_KEYWORDS = [
    "hi",
    "hello",
    "hey",
    "how are you",
    "thank you",
    "thanks",
    "who are you",
    "tell me a joke",
]

_GENERAL_KNOWLEDGE_PATTERNS = [
    r"\bwhat is\b",
    r"\bwho is\b",
    r"\bwhat are\b",
    r"\bhow does\b",
    r"\bwhy do\b",
    r"\bexplain\b",
]


def _has_phrase(text: str, phrases: Sequence[str]) -> Optional[str]:
    for p in phrases:
        if p in text:
            return p
    return None


def decide_answer_mode(
    user_query: str,
    chat_history: Optional[List[Dict]] = None,
    selected_docs_metadata: Optional[List[Dict]] = None,
) -> Dict:
    """
    Heuristic router for whether to run RAG or answer directly.
    - Defaults to RAG when uncertain to avoid hallucinations.
    - Honors explicit user overrides.
    """
    q = (user_query or "").strip()
    q_lower = q.lower()
    chat_history = chat_history or []
    selected_docs_metadata = selected_docs_metadata or []

    # --- explicit overrides ---
    if phrase := _has_phrase(q_lower, _OVERRIDE_RAG_PHRASES):
        return {
            "mode": "rag",
            "reason": f"User explicitly requested document-grounded answer via '{phrase}'.",
            "confidence": 0.95,
        }
    if phrase := _has_phrase(q_lower, _OVERRIDE_DIRECT_PHRASES):
        return {
            "mode": "direct",
            "reason": f"User explicitly requested a general answer via '{phrase}'.",
            "confidence": 0.95,
        }

    doc_score = 0.0
    direct_score = 0.0
    reasons: List[str] = []

    # --- document cues in current query ---
    if any(k in q_lower for k in _DOC_CUE_KEYWORDS):
        doc_score += 1.2
        reasons.append("Mentions document-specific cues (pages/sections/citations).")
    if re.search(r"\bpage\s+\d+", q_lower):
        doc_score += 1.0
        reasons.append("Asks about a specific page number.")
    if re.search(r"\bsection\s+[0-9ivx\.]+\b", q_lower):
        doc_score += 0.8
        reasons.append("Targets a specific section reference.")
    if any(k in q_lower for k in _DOC_SUMMARY_KEYWORDS):
        doc_score += 0.6
        reasons.append("Requests a summary/explanation of provided material.")

    # --- check for references to known doc metadata (filenames/sections) ---
    for meta in selected_docs_metadata:
        name = (meta.get("filename") or "").lower()
        title = (meta.get("title") or "").lower()
        if name and name in q_lower:
            doc_score += 0.8
            reasons.append(f"References uploaded file name '{name}'.")
        if title and title in q_lower:
            doc_score += 0.6
            reasons.append(f"References document title '{title}'.")

    # --- contextual cues from prior assistant message (follow-ups) ---
    last_assistant = next(
        (m.get("content", "") for m in reversed(chat_history) if m.get("role") == "assistant"),
        "",
    ).lower()
    if last_assistant:
        if "sources" in last_assistant or "page" in last_assistant:
            doc_score += 0.4
            reasons.append("Recent assistant turn referenced pages/sources (likely follow-up).")

    # --- general knowledge / small talk cues ---
    if _has_phrase(q_lower, _GENERAL_CHAT_KEYWORDS):
        direct_score += 1.1
        reasons.append("Looks like small talk or generic help.")

    if any(re.search(pat, q_lower) for pat in _GENERAL_KNOWLEDGE_PATTERNS):
        direct_score += 0.8
        reasons.append("Reads like a general knowledge question.")

    if "app" in q_lower or "button" in q_lower or "upload" in q_lower:
        direct_score += 0.4
        reasons.append("Asks about using the app rather than document content.")

    # --- decision (bias toward RAG when close) ---
    margin = direct_score - doc_score
    if margin > 0.35:
        mode = "direct"
    else:
        mode = "rag"

    # confidence is driven by margin magnitude, but never below 0.55
    confidence = 0.55 + min(abs(margin) * 0.25, 0.40)

    if not reasons:
        reasons.append("Defaulted to RAG to stay grounded when unsure.")

    return {
        "mode": mode,
        "reason": "; ".join(dict.fromkeys(reasons)),  # dedupe while preserving order
        "confidence": round(confidence, 2),
    }
