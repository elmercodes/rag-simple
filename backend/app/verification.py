import re

DEFAULT_REFUSAL = "I can’t find a supported answer in the provided document excerpts."

def _trim(text: str, max_chars: int = 7000) -> str:
    return (text or "")[:max_chars]

def verify_answer(
    *,
    client,
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
        "You are a judge evaluating whether an answer is supported by the provided document excerpts.\n"
        "Be strict enough to avoid hallucinations, but NOT overly strict.\n"
        "The assistant is allowed to use common sense and make reasonable assumptions ONLY if they are consistent with the excerpts.\n\n"
        "Your job:\n"
        "1) Decide if the DRAFT answers the QUESTION.\n"
        "2) Decide if the DRAFT is supported by the EXCERPTS.\n\n"
        "Verdicts:\n"
        "- SUPPORTED: answers the question and is supported (paraphrase ok).\n"
        "- PARTIAL: some support exists, but incomplete or slightly speculative. Rewrite to hedge and be precise.\n"
        "- UNSUPPORTED: not enough support to answer. Use the refusal text.\n\n"
        "Output format EXACTLY:\n"
        "VERDICT: <SUPPORTED|PARTIAL|UNSUPPORTED>\n"
        "CONFIDENCE: <0.00-1.00>\n"
        "FINAL: <one paragraph final answer>\n"
    )

    judge_user = (
        f"REFUSAL_TEXT:\n{refusal_text}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"DRAFT:\n{draft}\n\n"
        f"EXCERPTS:\n{excerpts}\n"
    )

    resp = client.chat.completions.create(
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

    # Safety fallbacks:
    if not final:
        final = refusal_text if verdict == "UNSUPPORTED" else (draft or "")

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
