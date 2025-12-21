import re

DEFAULT_REFUSAL = "I can’t find a supported answer in the provided document excerpts."

def _trim(text: str, max_chars: int = 7000) -> str:
    return (text or "")[:max_chars]

def _judge_system_prompt(policy: str) -> str:
    final_rule = (
        "- FINAL must NOT mention the words: DRAFT, VERDICT, CONFIDENCE, judge, verifier.\n"
    )
    if policy == "research":
        final_rule += "- FINAL must NOT mention the word EXCERPTS.\n"
    else:
        final_rule += (
            "- FINAL may begin with \"Based on the excerpts,\" but otherwise should not mention EXCERPTS.\n"
        )

    base = (
        "You are verifying an assistant answer using document excerpts.\n\n"
        "Rules for FINAL:\n"
        "- FINAL must be a normal, natural assistant response to the user.\n"
        f"{final_rule}"
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
    if policy == "research":
        return (
            "You are verifying an assistant answer using research-paper excerpts.\n"
            "Be strict: require strong textual support for every key claim.\n"
            "If anything important is missing or speculative, choose UNSUPPORTED.\n\n"
            + base
        )
    if policy == "manual":
        return (
            "You are verifying an assistant answer using manual excerpts.\n"
            "Be strict about relevance: the answer must be clearly grounded in the excerpts.\n"
            "If the answer could have been written without reading the excerpts, choose UNSUPPORTED.\n"
            "If the excerpts are about a different topic than the draft, choose UNSUPPORTED.\n"
            "If the answer is generic and not grounded in the excerpts, choose UNSUPPORTED.\n"
            "Common sense is allowed only when it is clearly anchored to excerpt facts or procedures.\n"
            "If some support exists but details are thin, choose PARTIAL and provide a hedged answer.\n"
            "If the answer has virtually no connection to the excerpts, choose UNSUPPORTED.\n\n"
            + base
        )
    return (
        "You are verifying an assistant answer using general document excerpts.\n"
        "Be strict about relevance: the answer must be clearly grounded in the excerpts.\n"
        "If the answer could have been written without reading the excerpts, choose UNSUPPORTED.\n"
        "If the excerpts are about a different topic than the draft, choose UNSUPPORTED.\n"
        "If the answer is generic and not grounded in the excerpts, choose UNSUPPORTED.\n"
        "Common sense is allowed only when it is clearly anchored to excerpt facts.\n"
        "If the excerpts provide partial support, choose PARTIAL and hedge instead of refusing.\n"
        "If the answer has virtually no connection to the excerpts, choose UNSUPPORTED.\n\n"
        + base
    )

def verify_answer(
    *,
    chat_client,
    model: str,
    question: str,
    draft: str,
    context: str,
    evidence_hits,
    refusal_text: str = DEFAULT_REFUSAL,
    policy: str = "general",
):
    """
    Less-strict verifier:
    - Allows common-sense linking + reasonable assumptions consistent with excerpts
    - Focuses on: does it answer the QUESTION, and is it supported enough?
    Returns (final_answer, debug_dict)
    """

    # Keep the excerpt payload bounded for cost / context
    excerpts = _trim(context, 7000)

    judge_system = _judge_system_prompt(policy)

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
        if "draft" in low:
            return ""
        if "excerpts" in low:
            if policy == "research":
                return ""
            if not low.startswith("based on the excerpts"):
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

    if verdict == "PARTIAL" and policy != "research":
        if final and not final.lower().startswith("based on the excerpts"):
            final = f"Based on the excerpts, {final}"

    debug = {
        "verdict": verdict,
        "confidence": confidence,
        "raw": text,
    }
    return final, debug
