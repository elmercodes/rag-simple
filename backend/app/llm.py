import os
from typing import Any, Dict

from openai import OpenAI


def _get_secret(key: str) -> str | None:
    env_val = os.getenv(key)
    if env_val:
        return env_val
    try:
        import streamlit as st  # type: ignore
        return st.secrets.get(key)
    except Exception:
        return None


class ChatProvider:
    def chat_complete(
        self,
        *,
        messages,
        model: str,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ):
        raise NotImplementedError


class OpenAIProvider(ChatProvider):
    def __init__(self, api_key: str | None = None):
        key = api_key or _get_secret("OPENAI_API_KEY")
        if not key:
            raise ValueError("Missing OPENAI_API_KEY for OpenAI provider.")
        self.client = OpenAI(api_key=key)

    def chat_complete(
        self,
        *,
        messages,
        model: str,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ):
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)
        return self.client.chat.completions.create(**payload)


class VLLMProvider(ChatProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        url = base_url or _get_secret("VLLM_BASE_URL")
        if not url:
            raise ValueError("Missing VLLM_BASE_URL for vLLM provider.")
        key = api_key or _get_secret("VLLM_API_KEY") or "EMPTY"
        self.client = OpenAI(api_key=key, base_url=url)

    def chat_complete(
        self,
        *,
        messages,
        model: str,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ):
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)
        return self.client.chat.completions.create(**payload)


def get_chat_client(provider: str | None) -> ChatProvider:
    """
    Return a chat provider wrapper for the requested provider.
    Provider values (case-insensitive):
        - "openai" (default)
        - "qwen-3" -> vLLM endpoint serving Qwen models
        - "vllm" -> generic vLLM OpenAI-compatible endpoint
    """
    if not provider:
        return OpenAIProvider()

    name = provider.lower()
    if name == "openai":
        return OpenAIProvider()
    if name in ("qwen-3", "vllm"):
        return VLLMProvider()

    # Default to OpenAI for unknown provider strings.
    return OpenAIProvider()
