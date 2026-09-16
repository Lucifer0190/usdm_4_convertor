"""Extraction C3 — eligibility criteria + demographics.

Per DESIGN.md and USDM 4.0, eligibility criteria are stored as FREE TEXT (native
Boolean-logic modelling is a known gap in the standard and an industry-wide ~30%
task — we deliberately do not attempt AND/OR structuring here). We extract the
inclusion/exclusion lists verbatim and the planned age range / sex.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from usdm4_assure.contracts import Document

_AGE_RE = re.compile(r"aged?\s+(\d{1,3})\s*(?:to|-|–|through)\s*(\d{1,3})\s*years", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*\d+[.)]\s+")           # split on "1. " / "2) "
_STOP_RE = r"(?:exclusion criteria|schedule of activities|^\s*6\.|\Z)"


@dataclass
class EligibilityExtract:
    inclusion: list[str] = field(default_factory=list)
    exclusion: list[str] = field(default_factory=list)
    age_min: float | None = None
    age_max: float | None = None
    age_unit: str = "Years"
    sex: str = "ALL"
    confidence: float = 0.0
    decision: str = "review"


def _split_items(region: str) -> list[str]:
    """Split a criteria region into individual numbered items."""
    parts = _SPLIT_RE.split(region)
    out = []
    for p in parts:
        s = re.sub(r"\s+", " ", p).strip(" .;:")
        # drop headers / fragments
        if len(s) >= 8 and not s.lower().endswith("criteria"):
            out.append(s + "." if not s.endswith(".") else s)
    return out


def _region(text: str, start_label: str, stop_pat: str) -> str:
    m = re.search(rf"{start_label}\s*:?(?P<body>.*?){stop_pat}",
                  text, re.IGNORECASE | re.DOTALL)
    return m.group("body") if m else ""


def extract_eligibility(doc: Document) -> EligibilityExtract:
    e = EligibilityExtract()
    text = doc.full_text

    inc_region = _region(text, r"inclusion criteria", _STOP_RE)
    exc_region = _region(text, r"exclusion criteria",
                         r"(?:schedule of activities|^\s*6\.|\Z)")
    e.inclusion = _split_items(inc_region)
    e.exclusion = _split_items(exc_region)

    if m := _AGE_RE.search(text):
        e.age_min, e.age_max = float(m.group(1)), float(m.group(2))
    # sex: default ALL unless clearly restricted
    if re.search(r"\b(male participants only|men only)\b", text, re.IGNORECASE):
        e.sex = "MALE"
    elif re.search(r"\b(female participants only|women only)\b", text, re.IGNORECASE):
        e.sex = "FEMALE"

    n = len(e.inclusion) + len(e.exclusion)
    e.confidence = 0.8 if (n >= 2 and e.age_min is not None) else (0.6 if n else 0.0)
    e.decision = "auto_accept" if e.confidence >= 0.8 else "review"
    return e
