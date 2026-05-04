"""Unified LLM provider configuration for both summarizer and reviewer roles.

Provider precedence (first env var that's set wins):
    GROQ_API_KEY  >  ANTHROPIC_API_KEY  >  OPENAI_API_KEY  >  GEMINI_API_KEY  >  OLLAMA_HOST

Users can override the auto-picked model with `SUMMARIZER_MODEL` / `REVIEWER_MODEL`:
    REVIEWER_MODEL=anthropic:claude-sonnet-4-20250514
    SUMMARIZER_MODEL=gpt-4o-mini

The reviewer model string follows PydanticAI's `<provider>:<model>` convention.
The summarizer uses a direct OpenAI-compatible client (Groq, OpenAI, Ollama, or
Gemini's OpenAI-compat endpoint) — no tool use, just one-shot text generation.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

from openai import OpenAI


_PROVIDER_ORDER = (
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "OLLAMA_HOST",
)

_DEFAULT_REVIEWER_MODEL: Dict[str, str] = {
    "GROQ_API_KEY": "groq:llama-3.3-70b-versatile",
    "ANTHROPIC_API_KEY": "anthropic:claude-sonnet-4-20250514",
    "OPENAI_API_KEY": "openai:gpt-4o",
    "GEMINI_API_KEY": "google-gla:gemini-1.5-pro",
    "OLLAMA_HOST": "openai:llama3",
}


def detect_provider() -> str:
    """Return the name of the first configured provider env var.

    Raises:
        RuntimeError: if no supported provider is configured.
    """
    for var in _PROVIDER_ORDER:
        if os.getenv(var):
            return var
    raise RuntimeError(
        "No LLM provider configured. Set one of: "
        + ", ".join(_PROVIDER_ORDER)
        + ". For the demo, GROQ_API_KEY is recommended (free tier)."
    )


def get_reviewer_model() -> str:
    """Return the PydanticAI model string for the reviewer agent.

    Honors REVIEWER_MODEL if set; otherwise picks based on detected provider.
    """
    explicit = os.getenv("REVIEWER_MODEL")
    if explicit:
        return explicit
    provider = detect_provider()
    return _DEFAULT_REVIEWER_MODEL[provider]


def _summarizer_endpoint() -> Dict[str, str]:
    """Return base_url, api_key, and model for the summarizer's OpenAI client.

    Falls back to whichever provider has an OpenAI-compatible endpoint.
    """
    explicit_model = os.getenv("SUMMARIZER_MODEL")

    if os.getenv("GROQ_API_KEY"):
        return {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": os.environ["GROQ_API_KEY"],
            "model": explicit_model or "llama-3.1-8b-instant",
        }
    if os.getenv("OPENAI_API_KEY"):
        return {
            "base_url": "https://api.openai.com/v1",
            "api_key": os.environ["OPENAI_API_KEY"],
            "model": explicit_model or "gpt-4o-mini",
        }
    if os.getenv("GEMINI_API_KEY"):
        # Gemini exposes an OpenAI-compatible endpoint.
        return {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key": os.environ["GEMINI_API_KEY"],
            "model": explicit_model or "gemini-1.5-flash",
        }
    if os.getenv("OLLAMA_HOST"):
        host = os.environ["OLLAMA_HOST"].rstrip("/")
        return {
            "base_url": f"{host}/v1",
            "api_key": "ollama",
            "model": explicit_model or "llama3",
        }
    raise RuntimeError(
        "Summarizer requires an OpenAI-compatible provider. Set GROQ_API_KEY, "
        "OPENAI_API_KEY, GEMINI_API_KEY, or OLLAMA_HOST."
    )


def call_summarizer(prompt: str, system: Optional[str] = None) -> str:
    """Run a single-shot text completion via the summarizer model.

    Args:
        prompt: the user prompt to send.
        system: optional system message.

    Returns:
        The assistant's text reply, stripped. Empty string if the API returns no content.
    """
    cfg = _summarizer_endpoint()
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        temperature=0.2,
        max_tokens=600,
    )
    content = response.choices[0].message.content if response.choices else None
    return (content or "").strip()
