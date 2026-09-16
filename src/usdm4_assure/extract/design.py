"""Extraction C2 — study design skeleton (type, phase, intervention model, arms).

Deterministic parse of the synopsis/design prose. The arms parse is the novel bit:
a randomization sentence ("randomized 1:1:1 to A, B, or Placebo") yields the arm
list, and placebo/comparator language sets each arm's type.

Returns both:
  * scalar design FieldCandidates (studyType, interventionModel) for the Assurance layer
  * a structured arms list with a confidence + decision
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from usdm4_assure.contracts import Document, FieldCandidate
from usdm4_assure.llm.base import LLM

DESIGN_FIELDS = ["studyType", "interventionModel"]

_MODEL_RE = re.compile(
    r"\b(parallel|cross[- ]?over|single[- ]?group|factorial|sequential)\b", re.IGNORECASE)
_MODEL_NORM = {"parallel": "Parallel", "crossover": "Crossover",
               "cross-over": "Crossover", "cross over": "Crossover",
               "single-group": "Single Group", "single group": "Single Group",
               "factorial": "Factorial", "sequential": "Sequential"}


@dataclass
class DesignExtract:
    study_type: str = "Interventional"
    intervention_model: str | None = None
    arms: list[dict] = field(default_factory=list)
    arms_confidence: float = 0.0
    arms_decision: str = "review"
    arms_source: str = ""


def _arm_type(name: str) -> str:
    low = name.lower()
    if "placebo" in low:
        return "Placebo Comparator"
    if "active" in low or "comparator" in low or "standard of care" in low:
        return "Active Comparator"
    return "Experimental"


def _parse_arms(text: str) -> tuple[list[dict], str]:
    """Find the arm enumeration and split into arms.

    Anchors on an explicit 'arms:'/'groups:' cue (preferred) or a randomization
    ratio, so it does not misfire on incidental 'to' (e.g. 'moderate to severe').
    """
    # Preferred: "... one of N arms/groups: <A>, <B>, or <C>"
    m = re.search(r"\b(?:arms?|groups?|cohorts?)\b\s*:\s*(?P<list>[^.]+)", text, re.IGNORECASE)
    if not m:
        # Fallback: a randomization ratio followed by 'to <list>'
        m = re.search(r"\b\d+:\d+(?::\d+)*\b[^.]*?\bto\b(?P<list>[^.]+)", text, re.IGNORECASE)
    if not m:
        return [], ""
    span = m.group("list")
    span = re.sub(r"^\s*(one of\s+\w+\s+(?:arms?|groups?)\s*:?\s*)", "", span,
                  flags=re.IGNORECASE)
    # split on commas and 'or'/'and'
    parts = re.split(r",|\bor\b|\band\b", span)
    arms = []
    for p in parts:
        name = re.sub(r"\s+", " ", p).strip(" .:;")
        name = re.sub(r"^(the|a|an)\s+", "", name, flags=re.IGNORECASE).strip()
        if 2 <= len(name) <= 60 and not name.lower().startswith(("approximately",)):
            arms.append({"name": name.title() if name.islower() else name,
                         "type": _arm_type(name)})
    # dedupe preserving order
    seen, out = set(), []
    for a in arms:
        if a["name"].lower() not in seen:
            seen.add(a["name"].lower())
            out.append(a)
    return out, m.group(0)[:200]


def extract_design(doc: Document, metadata_vals: dict, llm: LLM) -> tuple[
        list[FieldCandidate], DesignExtract]:
    text = doc.full_text
    de = DesignExtract()
    cands: list[FieldCandidate] = []

    # study type — interventional if intervention/randomization language present
    is_interventional = bool(re.search(
        r"\b(randomi[sz]ed|treatment|intervention|dose|administered)\b", text, re.IGNORECASE))
    de.study_type = "Interventional" if is_interventional else "Observational"
    cands.append(FieldCandidate("studyType", de.study_type, "design-heuristic",
                                de.study_type, 1))

    # intervention model
    mm = _MODEL_RE.search(text)
    if mm:
        de.intervention_model = _MODEL_NORM.get(mm.group(1).lower().replace("-", " "),
                                                mm.group(1).title())
        cands.append(FieldCandidate("interventionModel", de.intervention_model,
                                    "design-heuristic", mm.group(0), 1))

    # arms
    arms, src = _parse_arms(text)
    de.arms, de.arms_source = arms, src
    if arms:
        # confidence: multiple arms cleanly parsed from an explicit ratio => higher
        ratio = bool(re.search(r"\b\d+:\d+(:\d+)+\b", text))
        de.arms_confidence = 0.8 if (ratio and len(arms) >= 2) else 0.55
        de.arms_decision = "auto_accept" if de.arms_confidence >= 0.8 else "review"
    return cands, de
