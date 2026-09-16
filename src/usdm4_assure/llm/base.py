"""LLM abstraction — one interface so any provider (or none) is swappable.

The Assurance layer treats an LLM as just another ensemble member, so the
interface is deliberately small.
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


class ModelTier(str, Enum):
    """Tiered thinking per DESIGN.md §4 — cheap to heavy."""
    HAIKU = "haiku"     # narrow/high-volume, no extended thinking
    SONNET = "sonnet"   # prose extraction, light thinking
    OPUS = "opus"       # SoA / reconcile / verify — hardest reasoning


# Task -> tier routing. The router logs which tier served each field.
TASK_TIER: dict[str, ModelTier] = {
    "classify": ModelTier.HAIKU,
    "term_lookup": ModelTier.HAIKU,
    "extract_prose": ModelTier.SONNET,
    "extract_metadata": ModelTier.SONNET,
    "soa": ModelTier.OPUS,
    "reconcile": ModelTier.OPUS,
    "verify": ModelTier.OPUS,
}


def tier_for(task: str) -> ModelTier:
    return TASK_TIER.get(task, ModelTier.SONNET)


@runtime_checkable
class LLM(Protocol):
    """Minimal LLM contract."""

    available: bool
    name: str

    def complete(self, prompt: str, *, task: str = "extract_prose",
                 system: str | None = None, max_tokens: int = 1024) -> str:
        ...
