import re
from typing import List, Optional

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
