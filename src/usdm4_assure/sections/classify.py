"""Deterministic section-title classification onto the four-axis taxonomy.

The reference extractor types a section by its top-level *number* (ICH M11
numbering: 5 = population, 8 = assessments, ...). That breaks on older sponsor
templates (Lilly's "5. Introduction", "6. Objectives"), so this classifier keys
on the *title words* of the section itself and falls back to inheriting its
parent's labels — never on the number.

Container semantics (why a child does not simply override its parent):

* ``appendix`` is a *sticky type*: "Appendix 3 > Clinical Laboratory Tests"
  stays an appendix (subtype ``lab_inventory``), so routes that prohibit
  appendix evidence also cover its children. ``summary`` is deliberately not
  sticky — ICH M11 puts the SoA at 1.3, under "1. Protocol Summary".
* ``amendment_history`` is a *sticky subtype*: everything under a protocol
  amendment summary/history is historic. An SoA re-printed inside it becomes
  ``soa_table_historic``, never ``soa_table_current`` — the currentness
  guarantee task 3.5's scope filter relies on.

Every label a rule can emit is checked against ``config/section_taxonomy.yaml``
at import time, so the vocabulary cannot silently drift from the config.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

TAXONOMY_PATH = Path(__file__).resolve().parents[3] / "config" / "section_taxonomy.yaml"

STICKY_TYPES = frozenset({"appendix"})
AMENDMENT = "amendment_history"


@dataclass(frozen=True)
class Labels:
    """The classifier's output for one section (``None`` = no signal on that axis)."""
    section_type: str | None = None
    section_subtype: str | None = None
    authority_surface: str | None = None

    @property
    def typed(self) -> bool:
        return self.section_type is not None


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    labels: Labels


def _rule(words: str, section_type: str | None, subtype: str | None = None,
          authority: str | None = "content_section") -> _Rule:
    return _Rule(re.compile(rf"\b(?:{words})", re.IGNORECASE),
                 Labels(section_type, subtype, authority))


# Ordered: first match on the section's OWN title wins. More specific phrases
# precede the generic words they contain (e.g. "discontinuation of study
# treatment" must hit disposition before "study treatment" hits interventions).
_RULES: list[_Rule] = [
    _rule(r"protocol amendment|summary of (?:key )?changes|amendment (?:history|summary)|"
          r"document history|overall rationale for (?:the )?(?:protocol )?amendment",
          "summary", AMENDMENT, "amendment_summary"),
    _rule(r"table of contents|list of (?:tables|figures|appendices)",
          "header", "table_of_contents", "page_furniture"),
    _rule(r"title page|investigator'?s? (?:agreement|signature|statement)|"
          r"sponsor (?:signature|approval)|protocol (?:approval|signature)",
          "header", None, "title_identity"),
    _rule(r"abbreviations?|glossary|definitions? of terms",
          "summary", "abbreviations", "abbreviation_section"),
    _rule(r"schedule of (?:activities|assessments|events)|study (?:flow ?chart|schedule)|"
          r"flow ?chart|time and events|visit schedule|study plan and timing",
          "assessments", "soa_main", "soa_table_current"),
    _rule(r"estimands?", "science", "estimands_table", "estimand_column"),
    _rule(r"objectives?|endpoints?", "science", "objectives_table", "objective_column"),
    _rule(r"synopsis|protocol summary|study summary", "summary"),
    _rule(r"references|bibliography", "references"),
    _rule(r"appendix|appendices|attachment|annex|supporting documentation", "appendix"),
    _rule(r"discontinuation|withdrawal|lost to follow|early termination|"
          r"participant disposition|completion of the study", "disposition"),
    _rule(r"sample size", "statistics", "sample_size", "sample_size_section"),
    _rule(r"analysis (?:sets?|populations?)|populations for analys",
          "statistics", "analysis_sets", "statistics_section"),
    _rule(r"interim analys", "statistics", "interim_analysis", "interim_analysis_section"),
    _rule(r"statistic|data analys|analysis methods?|statistical hypothes",
          "statistics", "general_statistics", "statistics_section"),
    _rule(r"committees?|governance|data monitoring|adjudication",
          "appendix", "committee_governance", "adjudication_committee"),
    # ICH M11 §10 "Supporting Documentation and Operational Considerations".
    _rule(r"ethics\b|ethical (?:conduct|considerations|and regulatory)|regulatory|data (?:management|handling|protection)|quality (?:control|assurance)|"
          r"informed consent|publication|record keeping|monitoring of the study|audits?\b",
          "appendix"),
    _rule(r"(?:inclusion|exclusion|eligibility) criteria|study population|"
          r"selection of (?:study )?(?:population|participants|patients|subjects)|"
          r"lifestyle (?:considerations|restrictions)|screen failures",
          "population"),
    _rule(r"study design|investigational plan|overall design|design of the study|"
          r"schema|scientific rationale for (?:the )?study design|end of study definition",
          "design"),
    _rule(r"study interventions?|study treatments?|investigational (?:product|medicinal)|"
          r"study drugs?|dosing|dosage|concomitant (?:therapy|medication)|"
          r"treatments? administered|blinding|randomi[sz]ation",
          "interventions"),
    _rule(r"pharmacokinetic|pharmacodynamic", "assessments", "pk_assessment", "assessment_prose"),
    _rule(r"tumou?r assessment|recist", "assessments", "tumor_assessment", "assessment_prose"),
    _rule(r"response criteria", "appendix", "response_criteria", "response_criteria_appendix"),
    _rule(r"clinical laboratory|laboratory (?:tests|assessments|evaluations)",
          "assessments", "lab_inventory", "assessment_prose"),
    _rule(r"assessments?|procedures|efficacy|safety|adverse events?|vital signs|"
          r"physical examination|electrocardiogram|biomarkers?|immunogenicity",
          "assessments", None, "assessment_prose"),
    _rule(r"introduction|background|rationale|benefit[/ ]risk", "introduction"),
]


@cache
def taxonomy() -> dict[str, list[str]]:
    """The four label vocabularies from ``config/section_taxonomy.yaml``."""
    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _check_rules_against_taxonomy() -> None:
    tax = taxonomy()
    for r in _RULES:
        for axis, value in (("canonical_section_type", r.labels.section_type),
                            ("section_subtype", r.labels.section_subtype),
                            ("authority_surface", r.labels.authority_surface)):
            if value is not None and value not in tax[axis]:
                raise ValueError(f"classifier label {value!r} is not in {axis} "
                                 f"of {TAXONOMY_PATH.name}")


_check_rules_against_taxonomy()


_APPENDIX_TITLE = re.compile(r"^\s*(?:appendix|attachment|annex)\b", re.IGNORECASE)


def classify_title(title: str) -> Labels:
    """Labels from the title's own words alone (``Labels()`` if no rule fires).

    A title that *starts* "Appendix/Attachment/Annex" is an appendix whatever
    else it says — "Appendix 1 Protocol Amendment History" keeps the
    ``amendment_history`` subtype but is typed ``appendix``, as the reference
    does for amendment history filed under section 10.
    """
    for r in _RULES:
        if r.pattern.search(title):
            if _APPENDIX_TITLE.match(title) and r.labels.section_type != "appendix":
                return Labels("appendix", r.labels.section_subtype, r.labels.authority_surface)
            return r.labels
    return Labels()


def resolve(own: Labels, parent: Labels | None) -> Labels:
    """Combine a section's own labels with its (already resolved) parent's.

    * No own signal → inherit the parent wholesale.
    * Parent in the sticky ``appendix`` type → keep the parent's type, take
      the child's subtype/authority (so "Appendix > Laboratory Tests" is an
      appendix with ``lab_inventory``).
    * Parent historic (``amendment_history``) → the child is historic too;
      an SoA under it is ``soa_table_historic``.
    """
    if parent is None:
        return own
    if not own.typed:
        return parent
    section_type = own.section_type
    subtype, authority = own.section_subtype, own.authority_surface
    if parent.section_type in STICKY_TYPES and section_type not in STICKY_TYPES:
        section_type = parent.section_type
    if parent.section_subtype == AMENDMENT:
        authority = ("soa_table_historic" if own.section_subtype in ("soa_main", "soa_followup")
                     else parent.authority_surface)
        subtype = AMENDMENT
    return Labels(section_type, subtype, authority)
