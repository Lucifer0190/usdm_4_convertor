"""Domain -> route mapping tables (task 3.3, DEVPLAN.md §3-A).

Ported near-verbatim from the reference extractor
(``Rewant's_USDM_Extractor/app/services/study_plan_generator.py``). Ported
code, no tests of its own per this project's porting rule; not wired into
the pipeline yet (Phase 3's section-graph work, CP3-B, does that).

Changes from the source: import path renamed to this project's
``sections.models``; the two version constants inlined (the source's
``app.services.study_runtime_compat`` module isn't ported); the ontology
JSON this reads (``load_pfizer_protocol_ontology``) doesn't exist in this
project, so it always falls back to the built-in defaults below — the
source's own except-branch already handles that gracefully, unchanged here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from usdm4_assure.sections.models import (
    DomainRoutePlan,
    RepairRule,
    RouteScopePlan,
    StudyExtractionPlan,
    StudyFingerprint,
    ValidationExpectation,
)

PFIZER_ONTOLOGY_VERSION = "2026-04-29"
STUDY_PLAN_SCHEMA_VERSION = "1.0"

_ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "data" / "pfizer_protocol_ontology.json"


@lru_cache(maxsize=1)
def load_pfizer_protocol_ontology() -> dict[str, Any]:
    try:
        return json.loads(_ONTOLOGY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — ontology file is optional; missing/malformed both fall back
        return {"version": PFIZER_ONTOLOGY_VERSION, "domain_defaults": {}, "study_archetypes": {}}


def _scope(**kwargs: list[str]) -> RouteScopePlan:
    return RouteScopePlan(**{key: list(value or []) for key, value in kwargs.items()})


def _domain_defaults(name: str, ontology: dict[str, Any]) -> dict[str, Any]:
    defaults = ontology.get("domain_defaults")
    if not isinstance(defaults, dict):
        return {}
    value = defaults.get(name)
    return dict(value) if isinstance(value, dict) else {}


def _make_domain_route(
    domain: str,
    *,
    ontology: dict[str, Any],
    section_hints: list[str] | None = None,
    allowed_source_surfaces: list[str] | None = None,
    negative_source_surfaces: list[str] | None = None,
    primary_scopes: list[RouteScopePlan] | None = None,
    supporting_scopes: list[RouteScopePlan] | None = None,
    prohibited_scopes: list[RouteScopePlan] | None = None,
    preferred_content_types: list[str] | None = None,
    table_first: bool = False,
    cross_reference_expansion: bool = False,
    fallback_order: list[str] | None = None,
    required_family_types: list[str] | None = None,
    dependency_family_types: list[str] | None = None,
    required_scope_axes: list[str] | None = None,
    requires_continuation_resolution: bool = False,
    requires_note_dependency_resolution: bool = False,
    requires_current_only: bool = False,
    notes: list[str] | None = None,
) -> DomainRoutePlan:
    defaults = _domain_defaults(domain, ontology)
    return DomainRoutePlan(
        domain=domain,
        section_hints=list(section_hints or defaults.get("section_hints") or []),
        allowed_source_surfaces=list(allowed_source_surfaces or defaults.get("allowed_source_surfaces") or []),
        negative_source_surfaces=list(negative_source_surfaces or []),
        primary_scopes=list(primary_scopes or []),
        supporting_scopes=list(supporting_scopes or []),
        prohibited_scopes=list(prohibited_scopes or []),
        preferred_content_types=list(preferred_content_types or []),
        table_first=bool(table_first),
        cross_reference_expansion=bool(cross_reference_expansion),
        fallback_order=list(fallback_order or ["primary_typed_scope", "supporting_sibling_scope", "semantic_fallback"]),
        required_family_types=list(required_family_types or []),
        dependency_family_types=list(dependency_family_types or []),
        required_scope_axes=list(required_scope_axes or []),
        requires_continuation_resolution=bool(requires_continuation_resolution),
        requires_note_dependency_resolution=bool(requires_note_dependency_resolution),
        requires_current_only=bool(requires_current_only),
        notes=list(notes or []),
    )


def generate_study_extraction_plan(
    *,
    fingerprint: StudyFingerprint,
    graph_summary: dict[str, Any] | None = None,
    table_inventory: list[dict[str, Any]] | None = None,
) -> StudyExtractionPlan:
    ontology = load_pfizer_protocol_ontology()
    routes: dict[str, DomainRoutePlan] = {}
    notes: list[str] = []

    appendix_science = fingerprint.science_layout == "appendix_partitioned_science"
    appendix_soa = fingerprint.schedule_layout in {"appendix_partitioned_soa", "arm_split_appendix_soa"}
    extension_soa = fingerprint.schedule_layout in {
        "blinded_extension_soa",
        "multi_part_extension_soa",
        "period_split_soa",
        "withdrawal_extension_soa",
    }
    multi_part = fingerprint.multi_part_study
    phase_partitioned_science = fingerprint.science_layout == "phase_partitioned_science"
    period_partitioned_science = fingerprint.science_layout in {
        "period_partitioned_science",
        "withdrawal_partitioned_science",
    }
    substudy_partitioned_science = fingerprint.science_layout in {
        "substudy_partitioned_science",
        "appendix_partitioned_science",
    }
    substudy_partitioned_soa = fingerprint.schedule_layout in {
        "substudy_partitioned_soa",
        "appendix_partitioned_soa",
    }
    phase_transition_soa = fingerprint.schedule_layout == "phase_transition_soa"
    maintenance_regimen = fingerprint.intervention_layout == "maintenance_regimen_with_supportive_care"
    blinded_titration = fingerprint.intervention_layout in {
        "blinded_titration",
        "blinded_titration_with_open_label_cohort",
        "period_switch_blinded_regimen",
        "withdrawal_titration",
    }
    physician_choice_regimen = fingerprint.intervention_layout == "physician_choice_comparator"
    oncology_response_support = fingerprint.study_archetype in {
        "multi_part_randomized_oncology",
        "maintenance_randomized_oncology",
        "physician_choice_comparator_oncology",
        "sli_plus_randomized_phase3",
        "phase1b_phase2_split",
    }
    arm_scopes = list(getattr(fingerprint, "arm_structure", []) or [])
    region_scopes = list(getattr(fingerprint, "region_structure", []) or [])
    required_design_partitions = list(getattr(fingerprint, "required_design_partitions", []) or [])
    complexity_level = str(getattr(fingerprint, "complexity_level", "") or "standard")
    source_document_type = str(getattr(fingerprint, "source_document_type", "") or "clinical_protocol")
    adaptation_tags = set(getattr(fingerprint, "adaptation_tags", []) or [])
    image_heavy_schema = "image_heavy_schema" in adaptation_tags
    split_schedule_families = "split_schedule_families" in adaptation_tags
    explicit_analysis_sets = "explicit_analysis_sets" in adaptation_tags
    testing_hierarchy = "testing_hierarchy" in adaptation_tags
    historical_amendment_appendix = "historical_amendment_appendix" in adaptation_tags
    regimen_family_interventions = "regimen_family_interventions" in adaptation_tags

    period_or_part_scopes: list[str] = []
    if fingerprint.study_archetype in {"master_vaccine_protocol", "vaccine_substudy_protocol"}:
        period_or_part_scopes = required_design_partitions or ["substudy_a", "substudy_b", "substudy_c"]
    elif fingerprint.study_archetype == "umbrella_substudy_protocol":
        period_or_part_scopes = required_design_partitions or ["substudy_a"]
    elif fingerprint.study_archetype == "seamless_phase2b3":
        period_or_part_scopes = required_design_partitions or ["phase_2b", "phase_3"]
    elif fingerprint.study_archetype == "blinded_extension_with_open_label_cohort":
        period_or_part_scopes = ["part_i", "part_ia", "part_ib", "part_ii", "extension_period", "open_label_cohort"]
    elif fingerprint.study_archetype == "period_split_blinded_extension":
        period_or_part_scopes = ["period_a", "period_b", "extension_period"]
    elif fingerprint.study_archetype == "randomized_withdrawal_extension":
        period_or_part_scopes = ["randomized_withdrawal", "dose_up_titration", "dose_down_titration", "extension_period"]
    elif fingerprint.study_archetype == "multi_part_randomized_oncology":
        period_or_part_scopes = ["part_1", "part_2", "extension_period"]
    elif fingerprint.study_archetype == "sli_plus_randomized_phase3":
        period_or_part_scopes = ["safety_lead_in", "phase_3", "cohort_3"]

    routes["study_header"] = _make_domain_route(
        "study_header",
        ontology=ontology,
        primary_scopes=[_scope(section_types=["header", "summary"], authority_surfaces=["title_identity"])],
        supporting_scopes=[_scope(section_types=["summary"])],
        prohibited_scopes=[_scope(section_types=["statistics", "assessments"])],
        notes=["Study identity should come from title-page and synopsis evidence only."],
    )
    routes["amendments"] = _make_domain_route(
        "amendments",
        ontology=ontology,
        primary_scopes=[_scope(section_subtypes=["amendment_history"], authority_surfaces=["amendment_table", "amendment_summary"])],
        supporting_scopes=[_scope(section_types=["header"], authority_surfaces=["title_identity"])],
        prohibited_scopes=[_scope(section_types=["science", "assessments"], source_surfaces=["schedule_table_historic"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        required_family_types=["current_amendment_summary", "prior_amendment_history"],
        required_scope_axes=["study_scope"],
        requires_continuation_resolution=True,
        notes=["Amendment retrieval should stay isolated from current scientific evidence."],
    )
    routes["design_structure"] = _make_domain_route(
        "design_structure",
        ontology=ontology,
        primary_scopes=[_scope(section_types=["design"], authority_surfaces=["schema_table", "content_section"], table_roles=["schema"])],
        supporting_scopes=[
            _scope(section_types=["interventions"], source_surfaces=["intervention_admin_table", "intervention_admin_section"])
        ],
        prohibited_scopes=[_scope(section_types=["appendix", "summary"], source_surfaces=["schedule_table_historic"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        required_family_types=["schema_figure", "schema_table"],
        dependency_family_types=["design_backbone_support", "intervention_regimen"],
        required_scope_axes=["study_scope", "arm_scope"],
        requires_continuation_resolution=True,
        requires_current_only=True,
        notes=["Design extraction should prefer schema and overall-design sections."],
    )
    if image_heavy_schema:
        routes["design_structure"].primary_scopes.insert(
            0,
            _scope(
                section_types=["design"],
                authority_surfaces=["schema_figure", "schema_table"],
                source_surfaces=["design_schema"],
                table_roles=["schema"],
            ),
        )
        routes["design_structure"].notes.append("Image-heavy schema pages are treated as authoritative design backbone evidence and should be read multimodally before prose fallback.")
    if multi_part or extension_soa or substudy_partitioned_soa or phase_transition_soa:
        routes["design_structure"].supporting_scopes.append(
            _scope(section_types=["summary", "design"], source_surfaces=["protocol_synopsis", "design_schema"])
        )
        routes["design_structure"].notes.append("Design route allows synopsis/design support to preserve part-specific or extension-period structure.")
    if period_or_part_scopes:
        routes["design_structure"].supporting_scopes.append(
            _scope(section_types=["design", "summary"], study_scopes=period_or_part_scopes, source_surfaces=["design_schema", "protocol_synopsis"])
        )
        routes["design_structure"].notes.append("Design route preserves part/period-specific structure when the protocol defines multiple study periods or cohorts.")
    if complexity_level in {"high", "very_high"}:
        routes["design_structure"].notes.append("Complex-study mode treats collapsed one-design output as repairable accuracy loss, not a final manual-review state.")

    routes["interventions"] = _make_domain_route(
        "interventions",
        ontology=ontology,
        primary_scopes=[_scope(section_types=["interventions"], source_surfaces=["intervention_admin_table", "intervention_admin_section"])],
        supporting_scopes=[_scope(section_types=["design"], source_surfaces=["design_schema"])],
        prohibited_scopes=[_scope(section_types=["appendix"], source_surfaces=["appendix_operational"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        required_family_types=["intervention_regimen"],
        dependency_family_types=["dose_modification_support", "intervention_supportive_context"],
        required_scope_axes=["study_scope", "arm_scope"],
        requires_continuation_resolution=True,
        requires_current_only=True,
        notes=["Intervention tables should be authoritative over free-text summaries."],
    )
    if blinded_titration:
        routes["interventions"].supporting_scopes.append(
            _scope(section_types=["interventions", "design"], source_surfaces=["dose_modification_section", "design_schema"])
        )
        routes["interventions"].notes.append("Blinded extension studies should preserve titration and dose-up/dose-down structure.")
    if maintenance_regimen:
        routes["interventions"].supporting_scopes.append(
            _scope(section_types=["interventions"], source_surfaces=["intervention_general_section", "dose_modification_section"])
        )
        routes["interventions"].notes.append("Maintenance oncology studies may require regimen and supportive-care context from administration and concomitant-therapy sections.")
    if physician_choice_regimen:
        routes["interventions"].supporting_scopes.extend(
            [
                _scope(section_types=["design"], source_surfaces=["design_schema"]),
                _scope(section_types=["interventions"], source_surfaces=["intervention_general_section", "dose_modification_section"]),
            ]
        )
        routes["interventions"].notes.append("Physician-choice comparator studies should preserve comparator-regimen context from both design rationale and intervention sections.")
    if regimen_family_interventions:
        routes["interventions"].supporting_scopes.append(
            _scope(
                section_types=["interventions", "design"],
                source_surfaces=["intervention_admin_table", "intervention_admin_section", "dose_modification_section", "design_schema"],
                arm_scopes=arm_scopes,
            )
        )
        routes["interventions"].notes.append("Regimen-family intervention mode preserves optional comparator components, investigator-choice regimens, and arm-specific regimen families.")
    if period_or_part_scopes:
        routes["interventions"].supporting_scopes.append(
            _scope(section_types=["interventions", "design"], study_scopes=period_or_part_scopes, source_surfaces=["intervention_admin_section", "dose_modification_section", "design_schema"])
        )
        routes["interventions"].notes.append("Intervention recovery keeps period/part-specific dosing and extension behavior explicit.")
    if arm_scopes:
        routes["interventions"].supporting_scopes.append(
            _scope(section_types=["interventions", "design"], arm_scopes=arm_scopes)
        )
        routes["interventions"].notes.append("Intervention recovery preserves arm-specific dosing and comparator structure when arms are split in the protocol.")

    routes["populations_eligibility"] = _make_domain_route(
        "populations_eligibility",
        ontology=ontology,
        primary_scopes=[
            _scope(section_types=["population"], source_surfaces=["eligibility_inclusion", "eligibility_exclusion"]),
            _scope(section_types=["statistics"], section_subtypes=["analysis_sets"], authority_surfaces=["analysis_sets_table"]),
        ],
        supporting_scopes=[_scope(section_types=["design"], source_surfaces=["design_schema"])],
        prohibited_scopes=[_scope(section_types=["appendix"], source_surfaces=["appendix_operational"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        required_family_types=["eligibility_criteria"],
        dependency_family_types=["analysis_set_table"],
        required_scope_axes=["study_scope"],
        requires_continuation_resolution=True,
        requires_current_only=True,
        notes=["Eligibility should stay Section 5-led with analysis-set support from statistics."],
    )
    routes["analysis_sets"] = _make_domain_route(
        "analysis_sets",
        ontology=ontology,
        allowed_source_surfaces=["analysis_sets_table", "estimands_section"],
        primary_scopes=[
            _scope(
                section_types=["statistics"],
                section_subtypes=["analysis_sets"],
                authority_surfaces=["analysis_sets_table"],
                table_roles=["analysis_sets"],
            )
        ],
        supporting_scopes=[
            _scope(section_types=["population"]),
        ],
        prohibited_scopes=[_scope(section_types=["appendix"], source_surfaces=["appendix_operational"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        required_family_types=["analysis_set_table"],
        dependency_family_types=["estimand_block", "testing_hierarchy_support"],
        required_scope_axes=["study_scope", "arm_scope"],
        requires_continuation_resolution=True,
        requires_current_only=True,
        notes=["Analysis populations should come from explicit Section 9.2 style analysis-set evidence before any population prose fallback."],
    )
    if period_or_part_scopes:
        routes["analysis_sets"].supporting_scopes.append(
            _scope(
                section_types=["statistics", "design"],
                section_subtypes=["analysis_sets", "estimands_table"],
                study_scopes=period_or_part_scopes,
                source_surfaces=["analysis_sets_table", "estimands_section", "design_schema"],
            )
        )
        routes["analysis_sets"].notes.append("Analysis-set routing preserves part/period-specific populations when the protocol splits study portions or cohorts.")
    if arm_scopes:
        routes["analysis_sets"].supporting_scopes.append(
            _scope(section_types=["statistics", "design"], arm_scopes=arm_scopes)
        )
        routes["analysis_sets"].notes.append("Analysis-set routing preserves arm- or cohort-scoped populations when the source table distinguishes them.")
    if historical_amendment_appendix:
        routes["analysis_sets"].notes.append("Historical amendment appendix content should not replace current analysis-set definitions unless the current definition pages are absent.")

    objective_supporting_scopes = [_scope(section_types=["statistics"], section_subtypes=["endpoint_analysis"])]
    objective_allowed_surfaces = [
        "objectives_section",
        "endpoints_section",
        "estimands_section",
        "endpoint_analysis_section",
    ]
    objective_primary_scopes = [
        _scope(
            section_types=["science"],
            section_subtypes=["objectives_table", "estimands_table"],
            authority_surfaces=["objective_column", "endpoint_column", "estimand_column"],
            table_roles=["objective_endpoint_estimand"],
        )
    ]
    if substudy_partitioned_science and period_or_part_scopes:
        objective_primary_scopes.insert(
            0,
            _scope(
                section_types=["science", "appendix"],
                section_subtypes=["objectives_table", "estimands_table", "substudy_design"],
                authority_surfaces=["objective_column", "endpoint_column", "estimand_column"],
                table_roles=["objective_endpoint_estimand"],
                study_scopes=period_or_part_scopes,
            ),
        )
        objective_supporting_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics", "appendix"],
                section_subtypes=["objectives_table", "estimands_table", "endpoint_analysis", "substudy_design"],
                study_scopes=period_or_part_scopes,
            ),
        )
        objective_allowed_surfaces.extend(["appendix_substudy", "protocol_synopsis"])
        notes.append("Substudy science mode preserves objectives/endpoints by substudy, group, or master-protocol child context.")
    elif appendix_science:
        objective_supporting_scopes.insert(0, _scope(section_types=["appendix"], study_scopes=["substudy", "umbrella"]))
        notes.append("Science layout is appendix-partitioned; plan allows appendix science support.")
        objective_allowed_surfaces = [
            "objectives_section",
            "endpoints_section",
            "estimands_section",
            "endpoint_analysis_section",
            "appendix_substudy"
        ]
    if phase_partitioned_science:
        objective_supporting_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["objectives_table", "estimands_table", "endpoint_analysis"],
                phase_scopes=list(fingerprint.phase_structure),
            ),
        )
        notes.append("Science layout is phase-partitioned; retrieval should preserve phase/part-specific objective families.")
    if period_partitioned_science and period_or_part_scopes:
        objective_primary_scopes.insert(
            0,
            _scope(
                section_types=["science"],
                section_subtypes=["objectives_table", "estimands_table"],
                authority_surfaces=["objective_column", "endpoint_column", "estimand_column"],
                table_roles=["objective_endpoint_estimand"],
                study_scopes=period_or_part_scopes,
            ),
        )
        objective_supporting_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["objectives_table", "estimands_table", "endpoint_analysis"],
                study_scopes=period_or_part_scopes,
            ),
        )
        notes.append("Science layout is period-partitioned; retrieval should preserve Period/Part-specific objective families.")
    if oncology_response_support:
        objective_allowed_surfaces.append("response_criteria_appendix")
        objective_supporting_scopes.extend(
            [
                _scope(section_types=["assessments"], section_subtypes=["tumor_assessment"]),
                _scope(section_types=["appendix"], section_subtypes=["response_criteria"]),
            ]
        )
        notes.append("Oncology response-criteria support is enabled for endpoint-definition recovery.")
    if testing_hierarchy:
        objective_allowed_surfaces.extend(["interim_analysis_section", "sample_size_section"])
        objective_supporting_scopes.append(
            _scope(
                section_types=["statistics"],
                section_subtypes=["endpoint_analysis", "interim_analysis", "sample_size"],
                authority_surfaces=["endpoint_analysis_section", "interim_analysis_section", "sample_size_section"],
            )
        )
        notes.append("Statistics-driven testing hierarchy support is enabled so multiplicity and ordered-testing logic stay attached to science objects.")
    if region_scopes:
        objective_supporting_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["objectives_table", "estimands_table", "endpoint_analysis"],
                region_scopes=region_scopes,
            ),
        )
        notes.append("Objective and endpoint routing preserves region-partitioned science when US/global sections are separated.")
    routes["objectives_endpoints"] = _make_domain_route(
        "objectives_endpoints",
        ontology=ontology,
        allowed_source_surfaces=objective_allowed_surfaces,
        primary_scopes=objective_primary_scopes,
        supporting_scopes=objective_supporting_scopes,
        prohibited_scopes=[_scope(section_types=["appendix", "assessments"], source_surfaces=["appendix_operational"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        cross_reference_expansion=True,
        required_family_types=["science_row_family"],
        dependency_family_types=["science_hierarchy_support", "response_criteria_support"],
        required_scope_axes=["study_scope", "phase_scope", "arm_scope", "region_scope"],
        requires_continuation_resolution=True,
        requires_current_only=True,
        notes=["Objectives and endpoints should preserve table row identity before projection."],
    )
    routes["estimands"] = _make_domain_route(
        "estimands",
        ontology=ontology,
        allowed_source_surfaces=["estimands_section", "analysis_sets_table", "endpoint_analysis_section"],
        primary_scopes=[
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["estimands_table"],
                authority_surfaces=["estimand_column"],
                table_roles=["objective_endpoint_estimand"],
            ),
            _scope(section_types=["statistics"], section_subtypes=["analysis_sets"], authority_surfaces=["analysis_sets_table"]),
        ],
        supporting_scopes=[
            _scope(section_types=["statistics"], section_subtypes=["endpoint_analysis"]),
            _scope(section_types=["interventions"], source_surfaces=["dose_modification_section"]),
        ],
        prohibited_scopes=[_scope(section_types=["appendix"], source_surfaces=["appendix_operational"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        cross_reference_expansion=True,
        required_family_types=["estimand_block"],
        dependency_family_types=["analysis_set_table", "testing_hierarchy_support", "response_criteria_support"],
        required_scope_axes=["study_scope", "phase_scope", "arm_scope", "region_scope"],
        requires_continuation_resolution=True,
        requires_current_only=True,
        notes=["Estimands should be linked back to science rows and analysis sets."],
    )
    if phase_partitioned_science:
        routes["estimands"].supporting_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["estimands_table", "analysis_sets", "endpoint_analysis"],
                phase_scopes=list(fingerprint.phase_structure),
            ),
        )
        routes["estimands"].notes.append("Estimands should stay aligned to part/phase-specific science when the study splits objective families.")
    if period_partitioned_science and period_or_part_scopes:
        routes["estimands"].primary_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["estimands_table"],
                authority_surfaces=["estimand_column"],
                table_roles=["objective_endpoint_estimand"],
                study_scopes=period_or_part_scopes,
            ),
        )
        routes["estimands"].supporting_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["estimands_table", "analysis_sets", "endpoint_analysis"],
                study_scopes=period_or_part_scopes,
            ),
        )
        routes["estimands"].notes.append("Estimands should remain aligned to Period/Part-specific science when the study defines multiple study periods.")
    if region_scopes:
        routes["estimands"].supporting_scopes.insert(
            0,
            _scope(
                section_types=["science", "statistics"],
                section_subtypes=["estimands_table", "analysis_sets", "endpoint_analysis"],
                region_scopes=region_scopes,
            ),
        )
        routes["estimands"].notes.append("Estimands should preserve region-specific science boundaries when the protocol splits US/global families.")
    if testing_hierarchy:
        routes["estimands"].allowed_source_surfaces.extend(["interim_analysis_section", "sample_size_section"])
        routes["estimands"].supporting_scopes.append(
            _scope(
                section_types=["statistics"],
                section_subtypes=["endpoint_analysis", "interim_analysis", "sample_size"],
                authority_surfaces=["endpoint_analysis_section", "interim_analysis_section", "sample_size_section"],
            )
        )
        routes["estimands"].notes.append("Estimand recovery can use multiplicity and ordered-testing sections as support for hierarchy and linkage, without promoting pure power text into new estimands.")

    schedule_supporting_scopes = [_scope(section_types=["assessments"], authority_surfaces=["assessment_prose"])]
    schedule_allowed_surfaces = [
        "schedule_table_main",
        "schedule_table_followup",
        "schedule_notes_main",
        "dose_modification_section",
    ]
    schedule_primary_scopes = [
        _scope(section_types=["assessments"], section_subtypes=["soa_main", "soa_followup"], authority_surfaces=["soa_table_current"], table_roles=["soa"])
    ]
    if substudy_partitioned_soa and period_or_part_scopes:
        schedule_primary_scopes.insert(
            0,
            _scope(
                section_types=["assessments", "appendix"],
                section_subtypes=["soa_main", "soa_followup", "substudy_design"],
                authority_surfaces=["soa_table_current"],
                table_roles=["soa"],
                study_scopes=period_or_part_scopes,
            ),
        )
        schedule_supporting_scopes.insert(
            0,
            _scope(section_types=["appendix", "summary", "design"], study_scopes=period_or_part_scopes)
        )
        schedule_allowed_surfaces.extend(["appendix_substudy", "protocol_synopsis"])
        notes.append("Substudy schedule mode preserves substudy/group-specific SoA families and appendices.")
    elif appendix_soa:
        schedule_supporting_scopes.insert(0, _scope(section_types=["appendix"], study_scopes=["substudy", "followup_schedule"]))
        schedule_allowed_surfaces = [
            "schedule_table_main",
            "schedule_table_followup",
            "schedule_notes_main",
            "dose_modification_section",
            "appendix_substudy"
        ]
        notes.append("Schedule layout is appendix-heavy; plan widens allowed schedule surfaces.")
    elif extension_soa:
        schedule_supporting_scopes.extend(
            [
                _scope(section_types=["summary", "design"], source_surfaces=["protocol_synopsis", "design_schema"]),
                _scope(section_types=["interventions"], source_surfaces=["dose_modification_section"]),
            ]
        )
        schedule_allowed_surfaces = [
            "schedule_table_main",
            "schedule_table_followup",
            "schedule_notes_main",
            "dose_modification_section",
            "protocol_synopsis",
        ]
        notes.append("Blinded extension studies widen schedule support to extension and titration context.")
    if period_or_part_scopes:
        schedule_primary_scopes.insert(
            0,
            _scope(
                section_types=["assessments"],
                section_subtypes=["soa_main", "soa_followup"],
                authority_surfaces=["soa_table_current"],
                table_roles=["soa"],
                study_scopes=period_or_part_scopes,
            ),
        )
        schedule_supporting_scopes.extend(
            [
                _scope(section_types=["summary", "design"], study_scopes=period_or_part_scopes, source_surfaces=["protocol_synopsis", "design_schema"]),
                _scope(section_types=["interventions"], study_scopes=period_or_part_scopes, source_surfaces=["dose_modification_section", "intervention_admin_section"]),
            ]
        )
        notes.append("Schedule routing preserves part/period-specific visit families where the protocol splits periods or extension cohorts.")
    if phase_transition_soa:
        schedule_supporting_scopes.extend(
            [
                _scope(section_types=["statistics"], section_subtypes=["interim_analysis", "sample_size"]),
                _scope(section_types=["design", "summary"], source_surfaces=["design_schema", "protocol_synopsis"]),
            ]
        )
        notes.append("Phase-transition schedule mode keeps dose-selection, interim, and confirmatory timing context available for automatic recovery.")
    if arm_scopes:
        schedule_primary_scopes.insert(
            0,
            _scope(
                section_types=["assessments"],
                section_subtypes=["soa_main", "soa_followup"],
                authority_surfaces=["soa_table_current"],
                table_roles=["soa"],
                arm_scopes=arm_scopes,
            ),
        )
        schedule_supporting_scopes.append(
            _scope(section_types=["assessments", "design", "interventions"], arm_scopes=arm_scopes)
        )
        notes.append("Schedule routing preserves arm-specific visit families when Arm A/B or investigational/comparator schedules are split.")
    if split_schedule_families:
        notes.append("Schedule routing keeps distinct SoA table families separate when the protocol splits schedules by arm, cohort, control regimen, or study portion.")
    if oncology_response_support:
        schedule_allowed_surfaces.append("response_criteria_appendix")
        schedule_supporting_scopes.extend(
            [
                _scope(section_types=["assessments"], section_subtypes=["tumor_assessment"]),
                _scope(section_types=["appendix"], section_subtypes=["response_criteria"]),
            ]
        )
        notes.append("Oncology schedule routes can pull supportive timing and definition detail from tumor-assessment and response-criteria appendices.")
    routes["schedule_activities"] = _make_domain_route(
        "schedule_activities",
        ontology=ontology,
        allowed_source_surfaces=schedule_allowed_surfaces,
        primary_scopes=schedule_primary_scopes,
        supporting_scopes=schedule_supporting_scopes,
        prohibited_scopes=[_scope(section_subtypes=["amendment_history"], source_surfaces=["schedule_table_historic"])],
        preferred_content_types=["table", "table_row"],
        table_first=True,
        cross_reference_expansion=True,
        required_family_types=["schedule_matrix", "schedule_followup_matrix"],
        dependency_family_types=["schedule_notes", "schedule_appendix_support", "response_criteria_support"],
        required_scope_axes=["study_scope", "phase_scope", "arm_scope"],
        requires_continuation_resolution=True,
        requires_note_dependency_resolution=True,
        requires_current_only=True,
        notes=["Schedule extraction should preserve activity-by-visit matrix structure."],
    )
    if split_schedule_families:
        routes["schedule_activities"].notes.append("Distinct SoA table families must remain separate across arm, cohort, control-regimen, or portion-specific schedules even when activity names overlap.")
    if historical_amendment_appendix:
        routes["schedule_activities"].notes.append("Historical amendment appendix schedules are support only and must not overwrite the current final SoA matrices.")
    routes["organizations_sites"] = _make_domain_route(
        "organizations_sites",
        ontology=ontology,
        primary_scopes=[
            _scope(section_types=["header"], authority_surfaces=["title_identity"]),
            _scope(section_subtypes=["committee_governance"], authority_surfaces=["adjudication_committee"]),
        ],
        supporting_scopes=[_scope(section_types=["summary"])],
        prohibited_scopes=[_scope(section_types=["assessments", "statistics"])],
        notes=["Governance/committee sections may be supportive but not all administrative text implies StudySite objects."],
    )

    expectations = [
        ValidationExpectation(
            "required_standalone_protocol_source",
            "study_header",
            "high",
            "Full USDM extraction requires a standalone clinical protocol source document.",
            {"source_document_type": source_document_type},
        ),
        ValidationExpectation("required_primary_objective", "objectives_endpoints", "high", "A primary objective should exist for GSOP efficacy studies."),
        ValidationExpectation("required_primary_endpoint", "objectives_endpoints", "high", "A primary endpoint should exist for GSOP efficacy studies."),
        ValidationExpectation("required_schedule_matrix", "schedule_activities", "high", "Schedule should contain activity-by-visit mappings, not visit-only scaffolding."),
        ValidationExpectation(
            "required_schedule_link_integrity",
            "schedule_activities",
            "high",
            "Activities, encounters, and scheduled instances should stay mutually linked after projection.",
        ),
        ValidationExpectation("required_interventions", "interventions", "high", "At least one study intervention should be emitted.", {"min_count": 1}),
        ValidationExpectation(
            "required_design_backbone_links",
            "design_structure",
            "medium",
            "Arms should remain connected to cells, elements, and intervention backbone objects.",
        ),
        ValidationExpectation(
            "required_amendment_change_sections",
            "amendments",
            "medium",
            "Amendment changes should preserve normalized section references for downstream linking.",
        ),
    ]
    if fingerprint.stats_layout in {
        "explicit_estimands",
        "estimands_plus_analysis_sets",
        "analysis_sets_first",
        "estimands_analysis_sets_with_interims",
    } and not bool(getattr(fingerprint, "estimands_not_applicable", False)):
        expectations.append(
            ValidationExpectation("required_estimands", "estimands", "medium", "Explicit estimand studies should emit first-class Estimand objects.")
        )
        expectations.append(
            ValidationExpectation(
                "required_estimand_links",
                "estimands",
                "medium",
                "Explicit estimands should stay linked to endpoint and analysis-population objects.",
            )
        )
    if explicit_analysis_sets:
        expectations.append(
            ValidationExpectation(
                "required_analysis_sets",
                "analysis_sets",
                "high",
                "Protocols with explicit analysis-set tables should emit first-class AnalysisPopulation objects from the statistics surface.",
                {"min_count": 2},
            )
        )
    if testing_hierarchy:
        expectations.append(
            ValidationExpectation(
                "required_testing_hierarchy",
                "objectives_endpoints",
                "medium",
                "Statistics-driven protocols should preserve sequential or hierarchical testing order linked to endpoints and estimands.",
                {"min_count": 1},
            )
        )
    if image_heavy_schema:
        expectations.append(
            ValidationExpectation(
                "required_schema_figure_backbone",
                "design_structure",
                "high",
                "Figure-heavy schema studies should still emit a complete arm/cell/element backbone instead of falling back to prose-only design scaffolding.",
            )
        )
    if multi_part:
        expectations.append(
            ValidationExpectation("phase_or_substudy_partitioning", "design_structure", "medium", "Multi-part studies should preserve phase or substudy boundaries in extraction.")
        )
    if required_design_partitions:
        expectations.append(
            ValidationExpectation(
                "required_design_partitions",
                "design_structure",
                "high" if complexity_level in {"high", "very_high"} else "medium",
                "Complex protocols should preserve each detected phase, part, substudy, period, cohort, or group boundary in the USDM design graph.",
                {"partitions": required_design_partitions},
            )
        )
    if substudy_partitioned_science:
        expectations.append(
            ValidationExpectation(
                "required_substudy_partitioned_science",
                "objectives_endpoints",
                "high",
                "Master, umbrella, and vaccine-substudy protocols should keep science objects scoped to the correct substudy or group.",
                {"partitions": period_or_part_scopes},
            )
        )
    if phase_partitioned_science:
        expectations.append(
            ValidationExpectation("required_phase_partitioned_science", "objectives_endpoints", "high", "Phase- or part-split studies should keep science objects scoped to the right phase or part.")
        )
    if phase_transition_soa:
        expectations.append(
            ValidationExpectation(
                "required_phase_transition_schedule",
                "schedule_activities",
                "high",
                "Seamless or phase-transition protocols should keep dose-selection and confirmatory schedules separately recoverable.",
                {"partitions": period_or_part_scopes},
            )
        )
    if period_partitioned_science:
        expectations.append(
            ValidationExpectation("required_period_partitioned_science", "objectives_endpoints", "high", "Period- or extension-split studies should keep science objects scoped to the right period or cohort.")
        )
    if extension_soa:
        expectations.append(
            ValidationExpectation("required_extension_schedule", "schedule_activities", "medium", "Extension/titration studies should preserve the blinded core and extension schedule phases.")
        )
    if substudy_partitioned_soa:
        expectations.append(
            ValidationExpectation(
                "required_substudy_schedule",
                "schedule_activities",
                "high",
                "Master, umbrella, and vaccine-substudy protocols should preserve substudy/group-specific SoA families.",
                {"partitions": period_or_part_scopes},
            )
        )
    if maintenance_regimen:
        expectations.append(
            ValidationExpectation("required_comparator_regimen", "interventions", "medium", "Maintenance studies should preserve both investigational and comparator regimens.")
        )
    if physician_choice_regimen:
        expectations.append(
            ValidationExpectation("required_physician_choice_comparator", "interventions", "medium", "Physician-choice comparator studies should preserve explicit comparator regimen structure.")
        )

    repair_rules = [
        RepairRule(
            "repair_design_backbone_links",
            "design_structure",
            "Rebuild arm, cell, and element links from the recovered intervention backbone when projection weakens them.",
        ),
        RepairRule("backfill_primary_science", "objectives_endpoints", "Backfill missing primary objective or endpoint from authoritative science rows."),
        RepairRule("restore_schedule_matrix_links", "schedule_activities", "Expand visit-only schedule scaffolding into activity-by-visit mappings."),
        RepairRule("rebuild_analysis_sets", "populations_eligibility", "Rebuild named analysis populations from explicit analysis-set evidence."),
        RepairRule(
            "repair_amendment_section_links",
            "amendments",
            "Normalize amendment section references and attach deterministic links back to the affected study domains.",
        ),
    ]
    if explicit_analysis_sets:
        repair_rules.append(
            RepairRule(
                "rebuild_analysis_sets",
                "analysis_sets",
                "Rebuild named analysis populations directly from explicit analysis-set tables when eligibility or estimand projection flattens them.",
            )
        )
    if fingerprint.stats_layout in {
        "explicit_estimands",
        "estimands_plus_analysis_sets",
        "analysis_sets_first",
        "estimands_analysis_sets_with_interims",
    } and not bool(getattr(fingerprint, "estimands_not_applicable", False)):
        repair_rules.append(
            RepairRule("backfill_estimands", "estimands", "Recover missing estimands from explicit 9.1 definitions and linked science rows.")
        )
    if phase_partitioned_science:
        repair_rules.append(
            RepairRule("restore_phase_science_partition", "objectives_endpoints", "Recover phase- or part-specific objective and endpoint families when projection collapses them.")
        )
    if substudy_partitioned_science:
        repair_rules.append(
            RepairRule(
                "restore_substudy_science_partition",
                "objectives_endpoints",
                "Recover substudy/group-specific objective and endpoint families when projection collapses them.",
                "llm_pdf_refinement",
            )
        )
    if period_partitioned_science:
        repair_rules.append(
            RepairRule("restore_period_science_partition", "objectives_endpoints", "Recover period- or extension-specific objective and endpoint families when projection collapses them.")
        )
    if extension_soa:
        repair_rules.append(
            RepairRule("restore_extension_schedule", "schedule_activities", "Recover extension/titration visit families from SoA and design context.")
        )
    if substudy_partitioned_soa:
        repair_rules.append(
            RepairRule(
                "restore_substudy_schedule",
                "schedule_activities",
                "Recover substudy/group-specific SoA tables when projection collapses them.",
                "llm_pdf_refinement",
            )
        )
    if phase_transition_soa:
        repair_rules.append(
            RepairRule(
                "restore_phase_transition_schedule",
                "schedule_activities",
                "Recover phase-transition and dose-selection schedule families when projection collapses them.",
                "llm_pdf_refinement",
            )
        )
    if maintenance_regimen:
        repair_rules.append(
            RepairRule("restore_comparator_regimen", "interventions", "Recover maintenance-study comparator or supportive regimen context from authoritative intervention sections.")
        )
    if physician_choice_regimen:
        repair_rules.append(
            RepairRule("restore_physician_choice_regimen", "interventions", "Recover physician-choice comparator regimens from intervention and design evidence.")
        )

    if fingerprint.appendix_dependency_level == "high":
        notes.append("Plan permits appendix-first support for science and schedule because appendix dependency is high.")

    return StudyExtractionPlan(
        plan_version=STUDY_PLAN_SCHEMA_VERSION,
        ontology_version=str(ontology.get("version") or PFIZER_ONTOLOGY_VERSION),
        fingerprint=fingerprint,
        domain_routes=routes,
        negative_scopes=[_scope(section_subtypes=["amendment_history"], source_surfaces=["schedule_table_historic"])],
        required_expectations=expectations,
        repair_rules=repair_rules,
        confidence_notes=notes + list(fingerprint.rationale),
    )
