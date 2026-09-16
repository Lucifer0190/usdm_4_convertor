"""Shared data contracts that flow between layers.

These are the backbone: every module speaks in these types, which is what lets
the Assurance layer treat any extractor's output uniformly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# --------------------------------------------------------------------------- #
# Foundation (ingest)
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    """A positioned text block from the source PDF."""
    text: str
    page: int          # 1-indexed
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    kind: str = "prose"  # prose | heading | table | footnote


@dataclass
class Document:
    """The deterministic, cached result of ingest."""
    source: Path
    blocks: list[Block]
    full_text: str
    page_images: list[Path] = field(default_factory=list)

    def head_text(self, n_pages: int = 2) -> str:
        """Text of the first n pages — where study metadata usually lives."""
        return "\n".join(b.text for b in self.blocks if b.page <= n_pages)


# --------------------------------------------------------------------------- #
# Extraction -> Assurance
# --------------------------------------------------------------------------- #
@dataclass
class FieldCandidate:
    """One value for one field, produced by ONE extraction method.

    The Assurance layer's whole job is to reconcile multiple of these per field.
    """
    field: str                 # e.g. "studyTitle"
    value: str | None
    method: str                # e.g. "labels" | "titlepage" | "claude"
    source_text: str = ""      # the span this value was drawn from (for the verifier)
    source_page: int | None = None


class Decision(str, Enum):
    AUTO_ACCEPT = "auto_accept"   # ensemble agreed + verifier supported
    REVIEW = "review"             # disagreement or unsupported -> human
    BLOCK = "block"               # nothing found / hard fail


@dataclass
class AssuredField:
    """A field after the Assurance layer: scored, triaged, provenance-tagged."""
    field: str
    value: str | None
    candidates: list[FieldCandidate]
    methods_agree: bool
    n_methods: int
    verifier: str               # supported | partial | unsupported | n/a
    confidence: float           # 0..1, calibrated intent
    decision: Decision

    def as_review_row(self) -> dict:
        return {
            "field": self.field,
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "decision": self.decision.value,
            "methods_agree": self.methods_agree,
            "n_methods": self.n_methods,
            "verifier": self.verifier,
            "sources": [
                {"method": c.method, "page": c.source_page,
                 "value": c.value, "span": c.source_text[:160]}
                for c in self.candidates
            ],
        }
