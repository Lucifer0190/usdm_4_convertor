"""Shard definitions for two-pass sharded LLM extraction (DESIGN.md L4).

A shard is a small, named group of fields the LLM is asked about in one
two-pass call (:mod:`usdm4_assure.llm.two_pass`): free-text reasoning first,
then a strict JSON pass where every value must carry a supporting quote. Each
shard stays well under the 40-field ceiling the plan sets, so a single call's
JSON output stays small and easy to validate.

Field lists here are the canonical ones for C1/C2 (imported by the extractors
themselves, so there is exactly one source of truth); C3/C4 do not yet have a
canonical scalar field list of their own (their deterministic extractors work
in terms of structured lists — inclusion/exclusion items, objective/endpoint
pairs — rather than single fields), so this module defines the LLM-facing
scalar view for them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from usdm4_assure.extract.design import DESIGN_FIELDS
from usdm4_assure.extract.metadata import FIELDS as METADATA_FIELDS

# Hard ceiling from the plan: a shard's JSON output must stay reviewable in
# one pass. Enforced by a module-level check below, not just documentation.
MAX_SHARD_FIELDS = 40

ELIGIBILITY_FIELDS = [
    "inclusionCriteria",   # verbatim inclusion-criteria text (may be multi-item)
    "exclusionCriteria",   # verbatim exclusion-criteria text (may be multi-item)
    "plannedMinimumAge",   # e.g. "18"
    "plannedMaximumAge",   # e.g. "65"
    "plannedSex",          # ALL | MALE | FEMALE
]

OBJECTIVES_FIELDS = [
    "primaryObjective",
    "primaryEndpoint",
    "secondaryObjective",
    "secondaryEndpoint",
]


@dataclass(frozen=True)
class Shard:
    """One two-pass LLM call's worth of fields.

    Attributes:
        id: Stable identifier, also the prompt-template basename
            (``llm/prompts/<id>.pass1.md`` / ``<id>.pass2.md``).
        domain: Extraction domain this shard belongs to (matches
            ``GroundedCandidate.domain`` / ``AssuredField.domain``).
        fields: The field names the model is asked to return.
        description: One line of context injected into both prompt passes.
    """
    id: str
    domain: str
    fields: list[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        if len(self.fields) > MAX_SHARD_FIELDS:
            raise ValueError(
                f"shard {self.id!r} has {len(self.fields)} fields, "
                f"exceeding the {MAX_SHARD_FIELDS}-field ceiling")
        if not self.fields:
            raise ValueError(f"shard {self.id!r} has no fields")


SHARD_C1_METADATA = Shard(
    id="c1_metadata", domain="metadata", fields=list(METADATA_FIELDS),
    description="study identification metadata (title, sponsor, phase, identifiers)")

SHARD_C2_DESIGN = Shard(
    id="c2_design", domain="design", fields=list(DESIGN_FIELDS),
    description="study design classification (interventional/observational, "
               "intervention model)")

SHARD_C3_ELIGIBILITY = Shard(
    id="c3_eligibility", domain="eligibility", fields=list(ELIGIBILITY_FIELDS),
    description="eligibility criteria and planned demographics")

SHARD_C4_OBJECTIVES = Shard(
    id="c4_objectives", domain="objectives", fields=list(OBJECTIVES_FIELDS),
    description="study objectives and their linked endpoints")

ALL_SHARDS: list[Shard] = [
    SHARD_C1_METADATA, SHARD_C2_DESIGN, SHARD_C3_ELIGIBILITY, SHARD_C4_OBJECTIVES,
]

SHARDS_BY_DOMAIN: dict[str, list[Shard]] = {}
for _s in ALL_SHARDS:
    SHARDS_BY_DOMAIN.setdefault(_s.domain, []).append(_s)
