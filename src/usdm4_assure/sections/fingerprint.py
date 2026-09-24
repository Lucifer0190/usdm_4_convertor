"""Study fingerprint (task 3.4) — deterministic signals first, family YAML order.

The archetype is the first family in ``config/protocol_families.yaml`` whose
``match`` regexes all hit its ``where`` text (title pages or section titles).
Nothing matching → the YAML's first family (the source's default) with a
low confidence and a rationale that says it was defaulted, so a reviewer can
tell a detected archetype from a fallback.

The layout axes the ported planner branches on (``science_layout``,
``schedule_layout``, ...) stay at their neutral values unless this module has a
direct signal for them: switching the planner into a partitioned mode on a
guess would route evidence *more* narrowly than the protocol warrants.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from usdm4_assure.contracts import Document
from usdm4_assure.sections.graph import SectionGraph
from usdm4_assure.sections.models import StudyFingerprint

FAMILIES_PATH = Path(__file__).resolve().parents[3] / "config" / "protocol_families.yaml"

DETECTED_CONFIDENCE = 0.7
DEFAULT_CONFIDENCE = 0.4

# "Phase 1b/2", "Phase 2/3", "Phase IIb/III": one phase token or a slash list.
_PHASE_TOKEN = r"(?:[1-4]|iv|i{1,3})[ab]?"
_PHASE_RE = re.compile(rf"\bphase\s+({_PHASE_TOKEN}(?:\s*/\s*{_PHASE_TOKEN})*)\b", re.IGNORECASE)
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}
_DOMAINS = ["study_header", "design_structure", "interventions", "populations_eligibility",
            "objectives_endpoints", "schedule_activities"]


@dataclass(frozen=True)
class Family:
    key: str
    multi_part_study: bool
    rationale: str
    where: str = "title"
    match: tuple[str, ...] = ()

    def matches(self, texts: dict[str, str]) -> bool:
        text = texts.get(self.where, "")
        return bool(self.match) and all(re.search(p, text, re.IGNORECASE) for p in self.match)


@cache
def families() -> list[Family]:
    raw = yaml.safe_load(FAMILIES_PATH.read_text(encoding="utf-8"))["families"]
    return [Family(key=f["key"], multi_part_study=bool(f["multi_part_study"]),
                   rationale=str(f["rationale"]).strip(), where=f.get("where", "title"),
                   match=tuple(f.get("match") or ())) for f in raw]


def detect_family(texts: dict[str, str]) -> tuple[Family, bool]:
    """``(family, detected)``; ``detected`` is ``False`` for the fallback."""
    fams = families()
    for fam in fams:
        if fam.matches(texts):
            return fam, True
    return fams[0], False


def phases(text: str) -> list[str]:
    """Phase scopes named in ``text`` in first-seen order; only ``1b`` keeps its letter."""
    out: list[str] = []
    for m in _PHASE_RE.finditer(text):
        for tok in re.split(r"\s*/\s*", m.group(1).lower()):
            num = tok.rstrip("ab")
            key = f"phase_{_ROMAN.get(num, num)}"
            if key == "phase_1" and tok.endswith("b"):
                key = "phase_1b"
            if key not in out:
                out.append(key)
    return out


def fingerprint(doc: Document, graph: SectionGraph, document_id: int = 0) -> StudyFingerprint:
    title_text = doc.head_text(1)
    texts = {"title": title_text, "phases": " ".join(phases(title_text)),
             "sections": "\n".join(s.title for s in graph.sections)}
    fam, detected = detect_family(texts)

    subtypes = {s.section_subtype for s in graph.sections}
    tags = []
    if any(s.section_type == "appendix" and s.section_subtype == "amendment_history"
           for s in graph.sections):
        tags.append("historical_amendment_appendix")
    if "analysis_sets" in subtypes:
        tags.append("explicit_analysis_sets")
    science_in_appendix = any(
        s.section_type == "appendix" and s.section_subtype in ("soa_main", "objectives_table")
        for s in graph.sections)

    rationale = [fam.rationale if detected else
                 f"No family signal matched; defaulted to {fam.key}. {fam.rationale}"]
    if graph.source == "none":
        rationale.append("No section graph could be built; fingerprint uses title text only.")

    return StudyFingerprint(
        document_id=document_id,
        study_archetype=fam.key,
        design_mode="multi_part_design" if fam.multi_part_study else "single_design",
        science_layout="standard_science",
        schedule_layout="standard_soa",
        intervention_layout="standard_regimen",
        stats_layout="explicit_estimands" if "estimands_table" in subtypes else "standard_statistics",
        appendix_dependency_level="high" if science_in_appendix else "low",
        multi_part_study=fam.multi_part_study,
        estimands_not_applicable="estimands_table" not in subtypes,
        phase_structure=phases(title_text),
        expected_domains=list(_DOMAINS),
        adaptation_tags=tags,
        planner_mode="rule_only",
        confidence=DETECTED_CONFIDENCE if detected else DEFAULT_CONFIDENCE,
        rationale=rationale,
    )
