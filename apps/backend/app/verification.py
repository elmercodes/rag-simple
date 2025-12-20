import re

DEFAULT_REFUSAL = "I can’t find a supported answer in the provided document excerpts."

def _trim(text: str, max_chars: int = 7000) -> str:
    return (text or "")[:max_chars]

def verify_answer(
    *,
    chat_client,
    model: str,
    question: str,
    draft: str,
    context: str,
    evidence_hits,
    refusal_text: str = DEFAULT_REFUSAL,
):
    """
    Less-strict verifier:
    - Allows common-sense linking + reasonable assumptions consistent with excerpts
    - Focuses on: does it answer the QUESTION, and is it supported enough?
    Returns (final_answer, debug_dict)
    """

    # Keep the excerpt payload bounded for cost / context
    excerpts = _trim(context, 7000)

    judge_system = (
        "You are verifying an assistant answer using academic document excerpts.\n\n"
        "Rules for FINAL:\n"
        "- FINAL must be a normal, natural assistant response to the user.\n"
        "- FINAL must NOT mention the words: DRAFT, EXCERPTS, VERDICT, CONFIDENCE, judge, verifier.\n"
        "- FINAL must NOT talk about what is supported/unsupported. Just answer normally.\n"
        "- If unsupported, FINAL must be exactly the refusal text.\n\n"
        "Grounding rules:\n"
        "- Allow paraphrase and synthesis across excerpts.\n"
        "- Do NOT require verbatim matches.\n\n"
        "Output format EXACTLY:\n"
        "VERDICT: <SUPPORTED|PARTIAL|UNSUPPORTED>\n"
        "CONFIDENCE: <0.00-1.00>\n"
        "FINAL: <one paragraph natural answer to the user>\n"
    )

    judge_user = (
        f"REFUSAL_TEXT:\n{refusal_text}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"DRAFT:\n{draft}\n\n"
        f"EXCERPTS:\n{excerpts}\n"
    )

    resp = chat_client.chat_complete(
        model=model,
        messages=[
            {"role": "system", "content": judge_system},
            {"role": "user", "content": judge_user},
        ],
        stream=False,
    )

    text = resp.choices[0].message.content or ""

    verdict = "UNSUPPORTED"
    confidence = 0.0
    final = refusal_text

    m_v = re.search(r"VERDICT:\s*(SUPPORTED|PARTIAL|UNSUPPORTED)", text)
    if m_v:
        verdict = m_v.group(1)

    m_c = re.search(r"CONFIDENCE:\s*([0-1](?:\.\d+)?)", text)
    if m_c:
        try:
            confidence = float(m_c.group(1))
        except:
            confidence = 0.0

    m_f = re.search(r"FINAL:\s*(.*)$", text, flags=re.S)
    if m_f:
        final = m_f.group(1).strip()

    BAD_PREFIXES = (
        "the draft",
        "draft is",
        "the provided material",
        "the excerpts",
        "the answer is",
        "this is supported",
        "supported by",
        "unsupported",
    )

    def _sanitize_final(text: str) -> str:
        t = (text or "").strip()
        low = t.lower()
        if any(low.startswith(prefix) for prefix in BAD_PREFIXES):
            return ""
        if "draft" in low or "excerpts" in low:
            return ""
        return t

    sanitized = _sanitize_final(final)
    if not sanitized and verdict != "UNSUPPORTED":
        sanitized = (draft or "").strip()
    if not sanitized:
        sanitized = refusal_text if verdict == "UNSUPPORTED" else (draft or "")
    final = sanitized

    # Safety fallbacks:
    if verdict == "UNSUPPORTED":
        final = refusal_text
    elif not final:
        final = draft or ""

    # IMPORTANT: if verdict is PARTIAL, never hard-refuse.
    # Keep a hedged answer instead.
    if verdict == "PARTIAL" and final.strip() == refusal_text:
        final = draft

    debug = {
        "verdict": verdict,
        "confidence": confidence,
        "raw": text,
    }
    return final, debug
