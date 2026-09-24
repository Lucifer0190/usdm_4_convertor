"""Shared models for study-adaptive USDM planning.

Ported near-verbatim from the reference extractor
(``Rewant's_USDM_Extractor/app/services/study_adaptation_models.py``) — see
PLAN.md §5 and DEVPLAN.md task 3.1. Ported code is not tested on its own.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DocumentGraphSummary:
    document_id: int
    chunk_count: int = 0
    table_chunk_count: int = 0
    page_count: int = 0
    section_type_counts: dict[str, int] = field(default_factory=dict)
    section_subtype_counts: dict[str, int] = field(default_factory=dict)
    source_surface_counts: dict[str, int] = field(default_factory=dict)
    authority_surface_counts: dict[str, int] = field(default_factory=dict)
    table_role_counts: dict[str, int] = field(default_factory=dict)
    phase_scope_counts: dict[str, int] = field(default_factory=dict)
    study_scope_counts: dict[str, int] = field(default_factory=dict)
    arm_scope_counts: dict[str, int] = field(default_factory=dict)
    region_scope_counts: dict[str, int] = field(default_factory=dict)
    label_counts: dict[str, int] = field(default_factory=dict)
    amendment_chunk_count: int = 0
    appendix_chunk_count: int = 0
    cross_reference_count: int = 0
    adaptation_signal_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DocumentGraphSummary:
        return cls(**dict(payload or {}))


@dataclass(slots=True)
class TableInventoryEntry:
    chunk_id: str
    page_start: int | None
    page_end: int | None
    section_path: str
    section_type: str
    section_subtype: str
    source_surface: str
    authority_surface: str
    table_role: str
    table_column_roles: list[str] = field(default_factory=list)
    study_scope: str = "main_study"
    phase_scope: str = "all"
    arm_scope: str = "all_arms"
    region_scope: str = "all_regions"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TableInventoryEntry:
        return cls(**dict(payload or {}))


@dataclass(slots=True)
class StudyFingerprint:
    document_id: int
    study_archetype: str
    design_mode: str
    science_layout: str
    schedule_layout: str
    intervention_layout: str
    stats_layout: str
    appendix_dependency_level: str
    multi_part_study: bool
    estimands_not_applicable: bool = False
    phase_structure: list[str] = field(default_factory=list)
    substudy_structure: list[str] = field(default_factory=list)
    arm_structure: list[str] = field(default_factory=list)
    region_structure: list[str] = field(default_factory=list)
    currentness_risk: str = "medium"
    expected_domains: list[str] = field(default_factory=list)
    adaptation_tags: list[str] = field(default_factory=list)
    source_document_type: str = "clinical_protocol"
    complexity_level: str = "standard"
    automation_policy: str = "autonomous_full_extraction"
    required_design_partitions: list[str] = field(default_factory=list)
    planner_mode: str = "rule_only"
    confidence: float = 0.0
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StudyFingerprint:
        return cls(**dict(payload or {}))


@dataclass(slots=True)
class RouteScopePlan:
    section_types: list[str] = field(default_factory=list)
    section_subtypes: list[str] = field(default_factory=list)
    authority_surfaces: list[str] = field(default_factory=list)
    source_surfaces: list[str] = field(default_factory=list)
    table_roles: list[str] = field(default_factory=list)
    study_scopes: list[str] = field(default_factory=list)
    phase_scopes: list[str] = field(default_factory=list)
    arm_scopes: list[str] = field(default_factory=list)
    region_scopes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RouteScopePlan:
        return cls(**dict(payload or {}))


@dataclass(slots=True)
class DomainRoutePlan:
    domain: str
    section_hints: list[str] = field(default_factory=list)
    allowed_source_surfaces: list[str] = field(default_factory=list)
    negative_source_surfaces: list[str] = field(default_factory=list)
    primary_scopes: list[RouteScopePlan] = field(default_factory=list)
    supporting_scopes: list[RouteScopePlan] = field(default_factory=list)
    prohibited_scopes: list[RouteScopePlan] = field(default_factory=list)
    preferred_content_types: list[str] = field(default_factory=list)
    table_first: bool = False
    cross_reference_expansion: bool = False
    fallback_order: list[str] = field(default_factory=list)
    required_family_types: list[str] = field(default_factory=list)
    dependency_family_types: list[str] = field(default_factory=list)
    required_scope_axes: list[str] = field(default_factory=list)
    requires_continuation_resolution: bool = False
    requires_note_dependency_resolution: bool = False
    requires_current_only: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["primary_scopes"] = [scope.to_dict() for scope in self.primary_scopes]
        payload["supporting_scopes"] = [scope.to_dict() for scope in self.supporting_scopes]
        payload["prohibited_scopes"] = [scope.to_dict() for scope in self.prohibited_scopes]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DomainRoutePlan:
        data = dict(payload or {})
        data["primary_scopes"] = [RouteScopePlan.from_dict(item) for item in list(data.get("primary_scopes") or []) if isinstance(item, dict)]
        data["supporting_scopes"] = [RouteScopePlan.from_dict(item) for item in list(data.get("supporting_scopes") or []) if isinstance(item, dict)]
        data["prohibited_scopes"] = [RouteScopePlan.from_dict(item) for item in list(data.get("prohibited_scopes") or []) if isinstance(item, dict)]
        return cls(**data)


@dataclass(slots=True)
class ValidationExpectation:
    key: str
    domain: str
    severity: str = "medium"
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ValidationExpectation:
        return cls(**dict(payload or {}))


@dataclass(slots=True)
class RepairRule:
    key: str
    domain: str
    description: str
    mode: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RepairRule:
        return cls(**dict(payload or {}))


@dataclass(slots=True)
class StudyExtractionPlan:
    plan_version: str
    ontology_version: str
    fingerprint: StudyFingerprint
    domain_routes: dict[str, DomainRoutePlan] = field(default_factory=dict)
    negative_scopes: list[RouteScopePlan] = field(default_factory=list)
    required_expectations: list[ValidationExpectation] = field(default_factory=list)
    repair_rules: list[RepairRule] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_version": self.plan_version,
            "ontology_version": self.ontology_version,
            "fingerprint": self.fingerprint.to_dict(),
            "domain_routes": {name: route.to_dict() for name, route in self.domain_routes.items()},
            "negative_scopes": [scope.to_dict() for scope in self.negative_scopes],
            "required_expectations": [item.to_dict() for item in self.required_expectations],
            "repair_rules": [item.to_dict() for item in self.repair_rules],
            "confidence_notes": list(self.confidence_notes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StudyExtractionPlan:
        data = dict(payload or {})
        return cls(
            plan_version=str(data.get("plan_version") or ""),
            ontology_version=str(data.get("ontology_version") or ""),
            fingerprint=StudyFingerprint.from_dict(dict(data.get("fingerprint") or {})),
            domain_routes={
                str(name): DomainRoutePlan.from_dict(route)
                for name, route in dict(data.get("domain_routes") or {}).items()
                if isinstance(route, dict)
            },
            negative_scopes=[
                RouteScopePlan.from_dict(item)
                for item in list(data.get("negative_scopes") or [])
                if isinstance(item, dict)
            ],
            required_expectations=[
                ValidationExpectation.from_dict(item)
                for item in list(data.get("required_expectations") or [])
                if isinstance(item, dict)
            ],
            repair_rules=[
                RepairRule.from_dict(item)
                for item in list(data.get("repair_rules") or [])
                if isinstance(item, dict)
            ],
            confidence_notes=list(data.get("confidence_notes") or []),
        )
