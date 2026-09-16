"""Extraction C4 — objectives and endpoints (Estimands deferred to Phase 2).

Extracts the primary (and any secondary) objective/endpoint text by label. Each
objective links to its endpoint, matching the USDM Objective -> Endpoint model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from usdm4_assure.contracts import Document


@dataclass
class ObjectivePair:
    objective: str
    endpoint: str | None
    level: str  # Primary | Secondary


@dataclass
class ObjectivesExtract:
    items: list[ObjectivePair] = field(default_factory=list)
    confidence: float = 0.0
    decision: str = "review"


def _label_value(text: str, label: str) -> str | None:
    m = re.search(rf"{label}\s*:?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if m:
        v = m.group(1).strip()
        return v or None
    return None


def extract_objectives(doc: Document) -> ObjectivesExtract:
    o = ObjectivesExtract()
    text = doc.full_text

    prim_obj = _label_value(text, r"primary objective")
    prim_end = _label_value(text, r"primary endpoint")
    if prim_obj:
        o.items.append(ObjectivePair(prim_obj, prim_end, "Primary"))

    sec_obj = _label_value(text, r"secondary objective")
    sec_end = _label_value(text, r"secondary endpoint")
    if sec_obj:
        o.items.append(ObjectivePair(sec_obj, sec_end, "Secondary"))

    if o.items:
        o.confidence = 0.8 if o.items[0].endpoint else 0.6
        o.decision = "auto_accept" if o.confidence >= 0.8 else "review"
    return o
