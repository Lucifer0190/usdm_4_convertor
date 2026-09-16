"""OpenRouter adapter — the project's default LLM gateway.

OpenRouter exposes an OpenAI-compatible endpoint that fronts many providers behind
one key, which lets the Assurance ensemble mix model *families* for error
independence. We default to Claude (per project direction) but any OpenRouter model
slug can be selected per member.

Model ids are OpenRouter slugs (verified against the live catalog) and can be
overridden via ``OPENROUTER_MODEL_{HAIKU,SONNET,OPUS}`` environment variables.
"""
from __future__ import annotations

import os

import requests

from usdm4_assure.llm.base import LLM, ModelTier, tier_for
from usdm4_assure.llm.config import openrouter_key

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Default Claude tier -> OpenRouter slug (current catalog).
_DEFAULT_TIER_MODEL: dict[ModelTier, str] = {
    ModelTier.HAIKU: "anthropic/claude-haiku-4.5",
    ModelTier.SONNET: "anthropic/claude-sonnet-4.5",
    ModelTier.OPUS: "anthropic/claude-opus-4.8",
}


def _tier_model(tier: ModelTier) -> str:
    return os.environ.get(f"OPENROUTER_MODEL_{tier.name}", _DEFAULT_TIER_MODEL[tier])


class OpenRouterLLM(LLM):
    """An LLM member served through OpenRouter.

    Args:
        model: Explicit OpenRouter slug to force one model for every task. When
            ``None`` the model is chosen per task from the Claude tier map.
        name: Ensemble-member tag recorded in provenance (default ``"claude"``
            since Claude is the default family).
        timeout: Per-request timeout in seconds.
    """

    def __init__(self, model: str | None = None, name: str = "claude",
                 timeout: float = 60.0) -> None:
        self.api_key = openrouter_key()
        self.available = bool(self.api_key)
        self.model = model
        self.name = name
        self.timeout = timeout

    def complete(self, prompt: str, *, task: str = "extract_prose",
                 system: str | None = None, max_tokens: int = 1024) -> str:
        """Call the model and return its text.

        Args:
            prompt: The user message.
            task: Logical task name; selects the Claude tier when ``model`` is
                unset (see ``llm.base.TASK_TIER``).
            system: Optional system prompt.
            max_tokens: Response token cap.

        Returns:
            The assistant message text (empty string if the response is empty).

        Raises:
            RuntimeError: If called without a key, or the HTTP call fails.
        """
        if not self.available:
            raise RuntimeError("OpenRouterLLM called without an OpenRouter key")
        model = self.model or _tier_model(tier_for(task))
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})

        resp = requests.post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Optional attribution headers OpenRouter recommends.
                "HTTP-Referer": "https://hexaware.com",
                "X-Title": "USDM4-Assure",
            },
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:200]}")
        choices = resp.json().get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""
