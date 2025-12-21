from backend.app.verification import DEFAULT_REFUSAL, _judge_system_prompt, verify_answer


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": type("Msg", (), {"content": content})()})()]


class _FakeChatClient:
    def __init__(self, content: str):
        self._content = content

    def chat_complete(self, model, messages, stream=False):
        return _FakeResponse(self._content)


def _assert_contains(prompt: str, needle: str):
    if needle not in prompt:
        raise AssertionError(f"Missing expected text: {needle}")


def test_prompt_relevance_gates():
    manual = _judge_system_prompt("manual")
    general = _judge_system_prompt("general")
    research = _judge_system_prompt("research")

    _assert_contains(
        manual,
        "If the answer could have been written without reading the excerpts, choose UNSUPPORTED.",
    )
    _assert_contains(
        general,
        "If the answer could have been written without reading the excerpts, choose UNSUPPORTED.",
    )
    if "could have been written without reading the excerpts" in research:
        raise AssertionError("Research prompt should not include manual/general relevance gate.")


def test_unsupported_forces_refusal():
    fake = _FakeChatClient(
        "VERDICT: UNSUPPORTED\nCONFIDENCE: 0.12\nFINAL: Here is a generic answer."
    )
    final, debug = verify_answer(
        chat_client=fake,
        model="test",
        question="Q",
        draft="D",
        context="C",
        evidence_hits=[],
        refusal_text=DEFAULT_REFUSAL,
        policy="manual",
    )
    if final != DEFAULT_REFUSAL:
        raise AssertionError("UNSUPPORTED verdict should return refusal text.")
    if debug.get("verdict") != "UNSUPPORTED":
        raise AssertionError("Expected UNSUPPORTED verdict in debug output.")


if __name__ == "__main__":
    test_prompt_relevance_gates()
    test_unsupported_forces_refusal()
    print("ok")
