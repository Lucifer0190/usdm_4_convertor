"""Page-selection heuristics (task 3.3, DEVPLAN.md §3-A).

Ported near-verbatim from the reference extractor
(``Rewant's_USDM_Extractor/app/services/hard_page_selector.py``). Ported
code, no tests of its own per this project's porting rule; not wired into
the pipeline yet (Phase 3's section-graph work, CP3-B, does that).

Changes from the source: the small data model it needs
(``HardPageEntry``/``PageFamily``/``HardPageManifest``, from the source's
``agentic_reading_models.py``) is inlined below rather than pulled in as a
separate module, since nothing else in this project uses it yet. The
``SourceFamily`` type (only used under ``TYPE_CHECKING`` in the source, from
its ``usdm_source_inventory.py``) isn't ported — that dependency isn't
needed at runtime, only for the type hint, so callers pass ``Any``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# --- data model (source: agentic_reading_models.py) ---------------------------- #


@dataclass(slots=True)
class HardPageEntry:
    """One full protocol page selected for agentic hard-section reading."""

    page: int
    authority: str
    score: int
    reasons: list[str] = field(default_factory=list)
    section_label: str = ""
    source_surface: str = ""
    section_path: str = ""
    phase_scope: str = "all"
    study_scope: str = "main_study"
    arm_scope: str = "all_arms"
    region_scope: str = "all_regions"
    currentness_tag: str = "unknown"
    source_family_ids: list[str] = field(default_factory=list)
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(dict.fromkeys(self.reasons))
        return payload


@dataclass(slots=True)
class PageFamily:
    """A contiguous family of full pages that should be read together."""

    family_id: str
    pages: list[int] = field(default_factory=list)
    authority: str = "supporting"
    reasons: list[str] = field(default_factory=list)
    section_labels: list[str] = field(default_factory=list)
    source_surfaces: list[str] = field(default_factory=list)
    phase_scope: str = "all"
    study_scope: str = "main_study"
    arm_scope: str = "all_arms"
    region_scope: str = "all_regions"
    currentness_tag: str = "unknown"
    source_family_ids: list[str] = field(default_factory=list)
    continuation_family_ids: list[str] = field(default_factory=list)
    dependency_family_ids: list[str] = field(default_factory=list)
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HardPageManifest:
    """Selected full pages and grouped page families for one profile."""

    profile_name: str
    pages: list[HardPageEntry] = field(default_factory=list)
    page_families: list[PageFamily] = field(default_factory=list)
    selection_reasons: list[str] = field(default_factory=list)

    def selected_pages(self) -> list[int]:
        return [entry.page for entry in self.pages]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "selection_reasons": list(dict.fromkeys(self.selection_reasons)),
            "pages": [entry.to_dict() for entry in self.pages],
            "page_families": [family.to_dict() for family in self.page_families],
        }


# --- heuristics (source: hard_page_selector.py) --------------------------------- #

_CURRENTNESS_SENSITIVE_PROFILES = {
    "analysis_sets",
    "design_structure",
    "interventions",
    "objectives_endpoints",
    "estimands",
    "populations_eligibility",
    "schedule_activities",
    "organizations_sites",
}
_HISTORICAL_MARKERS = (
    "protocol amendment history",
    "protocol amendment summary",
    "summary of changes",
    "document history",
    "prior amendment",
    "previous amendment",
    "superseded",
    "supersedes",
    "no longer applicable",
    "no longer pursued",
    "withdrawn",
    "retired",
    "deleted",
    "removed",
    "replaced by",
    "former arm",
    "former cohort",
    "former regimen",
    "historical",
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _entry_heading(entry: Any) -> str:
    heading_path = getattr(entry, "heading_path", None) or []
    if isinstance(heading_path, list):
        return " > ".join(_clean_text(item) for item in heading_path if _clean_text(item))
    return _clean_text(heading_path)


def _is_currentness_sensitive_profile(profile_name: Any) -> bool:
    return _clean_text(profile_name) in _CURRENTNESS_SENSITIVE_PROFILES


def _profile_chunk_text_map(bundle: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for chunk, _score in list(getattr(bundle, "chunks", []) or []):
        chunk_id = _clean_text(getattr(chunk, "id", ""))
        if chunk_id:
            mapping[chunk_id] = _clean_text(getattr(chunk, "content", ""))
    return mapping


def _entry_currentness(entry: Any, *, chunk_text: str = "") -> str:
    if entry is None:
        return "unknown"
    source_surface = _clean_text(getattr(entry, "source_surface", ""))
    authority_surface = _clean_text(getattr(entry, "authority_surface", ""))
    if source_surface == "schedule_table_historic" or authority_surface == "soa_table_historic":
        return "historical"
    lowered = " ".join(
        part.lower()
        for part in (
            _entry_heading(entry),
            _clean_text(getattr(entry, "table_parent", "")),
            _clean_text(chunk_text),
        )
        if part
    )
    if any(marker in lowered for marker in _HISTORICAL_MARKERS):
        return "historical"
    if source_surface in {
        "design_schema",
        "intervention_admin_table",
        "intervention_admin_section",
        "intervention_general_section",
        "analysis_sets_table",
    }:
        return "current"
    return "unknown"


def _score_entry(entry: Any, *, rank: int, preferred_label: str, preferred_surfaces: set[str]) -> int:
    score = max(1, 12 - rank)
    label = _clean_text(getattr(entry, "label", ""))
    source_surface = _clean_text(getattr(entry, "source_surface", ""))
    if preferred_label and label == preferred_label:
        score += 10
    if source_surface in preferred_surfaces:
        score += 12
    elif source_surface.endswith("_table_main"):
        score += 4
    if bool(getattr(entry, "is_amendment_summary", False)):
        score += 4
    return score


def _best_entry_for_page(section_map: Any, page: int, *, preferred_label: str, preferred_surfaces: set[str]) -> Any:
    best_entry = None
    best_score = -1
    entries = getattr(section_map, "entries", {}) or {}
    for entry in entries.values():
        if entry is None or bool(getattr(entry, "is_noise", False)):
            continue
        start = getattr(entry, "page_start", None)
        end = getattr(entry, "page_end", None) or start
        if start is None or end is None or not (int(start) <= page <= int(end)):
            continue
        score = _score_entry(
            entry,
            rank=1,
            preferred_label=preferred_label,
            preferred_surfaces=preferred_surfaces,
        )
        if score > best_score:
            best_score = score
            best_entry = entry
    return best_entry


def _build_page_families(
    entries: list[HardPageEntry],
    *,
    source_family_lookup: dict[str, Any] | None = None,
    required_family_ids: set[str] | None = None,
) -> list[PageFamily]:
    families: list[PageFamily] = []
    current: PageFamily | None = None
    previous: HardPageEntry | None = None
    source_family_lookup = source_family_lookup or {}
    required_family_ids = required_family_ids or set()
    for entry in sorted(entries, key=lambda item: item.page):
        same_family = current is not None and previous is not None and entry.page == previous.page + 1
        same_scope = current is not None and previous is not None and (
            previous.phase_scope == entry.phase_scope
            and previous.study_scope == entry.study_scope
            and previous.arm_scope == entry.arm_scope
            and previous.region_scope == entry.region_scope
            and previous.currentness_tag == entry.currentness_tag
        )
        same_surface = current is not None and previous is not None and (
            entry.section_label == previous.section_label
            or entry.source_surface == previous.source_surface
            or ("continuation_window" in entry.reasons and (not previous.section_label or not previous.source_surface))
            or ("continuation_window" in previous.reasons and (not entry.section_label or not entry.source_surface))
            or (not entry.section_label and not previous.section_label)
            or (not entry.source_surface and not previous.source_surface)
        )
        if not same_family or not same_scope or not same_surface:
            current = PageFamily(
                family_id=f"page_family_{len(families) + 1:03d}",
                pages=[entry.page],
                authority=entry.authority,
                reasons=list(entry.reasons),
                section_labels=[entry.section_label],
                source_surfaces=[entry.source_surface],
                phase_scope=entry.phase_scope,
                study_scope=entry.study_scope,
                arm_scope=entry.arm_scope,
                region_scope=entry.region_scope,
                currentness_tag=entry.currentness_tag,
                source_family_ids=list(entry.source_family_ids),
                required=bool(entry.required),
            )
            families.append(current)
        previous = entry
        if not same_family or not same_scope or not same_surface:
            continue
        current.pages.append(entry.page)
        if entry.authority == "authoritative":
            current.authority = "authoritative"
        current.reasons.extend(entry.reasons)
        current.section_labels.append(entry.section_label)
        current.source_surfaces.append(entry.source_surface)
        current.source_family_ids.extend(entry.source_family_ids)
        current.required = bool(current.required or entry.required)
    for family in families:
        continuation_ids: list[str] = []
        dependency_ids: list[str] = []
        for source_family_id in list(dict.fromkeys(family.source_family_ids)):
            source_family = source_family_lookup.get(source_family_id)
            if source_family is None:
                continue
            continuation_parent = _clean_text(getattr(source_family, "continuation_of_family_id", ""))
            if continuation_parent:
                continuation_ids.append(continuation_parent)
            dependency_ids.extend(list(getattr(source_family, "depends_on_family_ids", []) or []))
            dependency_ids.extend(list(getattr(source_family, "note_dependency_family_ids", []) or []))
        family.continuation_family_ids = list(dict.fromkeys(continuation_ids))
        family.dependency_family_ids = list(dict.fromkeys(_clean_text(value) for value in dependency_ids if _clean_text(value)))
        family.required = bool(family.required or bool(required_family_ids.intersection(set(family.source_family_ids))))
    return families


def build_hard_page_manifest(
    *,
    profile: Any,
    bundle: Any,
    section_map: Any,
    max_page_count: int,
    config: dict[str, Any],
    selection_reasons: list[str] | None = None,
    review_flags: list[dict[str, Any]] | None = None,
    source_families: list[Any] | None = None,
    target_family_ids: list[str] | None = None,
    restrict_to_target_families: bool = False,
    exact_target_pages: list[int] | None = None,
) -> HardPageManifest:
    preferred_label = _clean_text(config.get("section_label"))
    profile_name = _clean_text(getattr(profile, "name", ""))
    preferred_surfaces = {_clean_text(value) for value in config.get("source_surfaces", []) if _clean_text(value)}
    spillover_pages = max(0, int(config.get("spillover_pages", 0) or 0))
    max_pages = max(1, int(config.get("max_pages", 6) or 6))
    exact_target_pages = [int(page) for page in (exact_target_pages or []) if int(page) > 0]
    exact_target_page_set = set(exact_target_pages)
    if exact_target_page_set:
        spillover_pages = 0
        max_pages = max(1, len(exact_target_page_set))
    currentness_sensitive = _is_currentness_sensitive_profile(profile_name)
    chunk_text_map = _profile_chunk_text_map(bundle)
    page_entries: dict[int, HardPageEntry] = {}
    target_family_ids = [_clean_text(value) for value in (target_family_ids or []) if _clean_text(value)]
    target_family_lookup = {family.family_id: family for family in source_families or [] if _clean_text(family.family_id)}
    required_family_ids = set(target_family_ids)

    def register(
        page: int,
        *,
        score: int,
        entry: Any,
        reason: str,
        authority: str,
        source_family_ids: list[str] | None = None,
        force_required: bool = False,
    ) -> None:
        if page <= 0 or (max_page_count and page > max_page_count):
            return
        resolved_entry = entry or _best_entry_for_page(
            section_map,
            page,
            preferred_label=preferred_label,
            preferred_surfaces=preferred_surfaces,
        )
        current = page_entries.get(page)
        section_label = _clean_text(getattr(resolved_entry, "label", "")) if resolved_entry is not None else preferred_label
        source_surface = _clean_text(getattr(resolved_entry, "source_surface", "")) if resolved_entry is not None else ""
        section_path = _entry_heading(resolved_entry) if resolved_entry is not None else ""
        phase_scope = _clean_text(getattr(resolved_entry, "phase_scope", "")) or "all"
        study_scope = _clean_text(getattr(resolved_entry, "study_scope", "")) or "main_study"
        arm_scope = _clean_text(getattr(resolved_entry, "arm_scope", "")) or "all_arms"
        region_scope = _clean_text(getattr(resolved_entry, "region_scope", "")) or "all_regions"
        currentness_tag = _entry_currentness(
            resolved_entry,
            chunk_text=chunk_text_map.get(_clean_text(getattr(resolved_entry, "chunk_id", "")), ""),
        )
        source_family_ids = [_clean_text(value) for value in (source_family_ids or []) if _clean_text(value)]
        required = bool(force_required or required_family_ids.intersection(set(source_family_ids)))
        if source_family_ids:
            family_currentness = {
                target_family_lookup.get(family_id).currentness_tag
                for family_id in source_family_ids
                if target_family_lookup.get(family_id) is not None
            }
            if "current" in family_currentness:
                currentness_tag = "current"
            elif "historical" in family_currentness and currentness_tag != "current":
                currentness_tag = "historical"
        if currentness_sensitive and currentness_tag == "historical" and not reason.startswith("validation_hint"):
            score = max(1, score - 36)
            if reason != "historical_signal":
                reason = f"{reason}|historical_signal"
        elif currentness_sensitive and currentness_tag == "current":
            score += 4
        if current is None:
            page_entries[page] = HardPageEntry(
                page=page,
                authority=authority,
                score=score,
                reasons=[reason],
                section_label=section_label,
                source_surface=source_surface,
                section_path=section_path,
                phase_scope=phase_scope,
                study_scope=study_scope,
                arm_scope=arm_scope,
                region_scope=region_scope,
                currentness_tag=currentness_tag,
                source_family_ids=list(source_family_ids),
                required=required,
            )
            return
        current.score += score
        current.reasons.append(reason)
        if authority == "authoritative":
            current.authority = "authoritative"
        if not current.section_label and section_label:
            current.section_label = section_label
        if not current.source_surface and source_surface:
            current.source_surface = source_surface
        if not current.section_path and section_path:
            current.section_path = section_path
        if current.currentness_tag != "current" and currentness_tag:
            current.currentness_tag = currentness_tag
        current.source_family_ids.extend(source_family_ids)
        current.required = bool(current.required or required or force_required)

    source_families = list(source_families or [])
    if source_families:
        candidate_families = [
            family
            for family in source_families
            if family.domain == profile_name and (not target_family_ids or family.family_id in target_family_ids)
        ]
        for family in candidate_families:
            family_reason = "coverage_gap_family" if family.family_id in target_family_ids else "source_inventory"
            family_score = 38 if family.family_id in target_family_ids else 18
            family_surface = _clean_text(getattr(family, "source_surface", ""))
            family_authority_surface = _clean_text(getattr(family, "authority_surface", ""))
            family_label = _clean_text(getattr(family, "section_label", ""))
            family_currentness = _clean_text(getattr(family, "currentness_tag", ""))
            surface_matches_profile = bool(
                family_label == preferred_label
                or family_surface in preferred_surfaces
                or family_authority_surface in preferred_surfaces
            )
            force_required = bool(
                not exact_target_page_set
                and config.get("select_on_surface")
                and surface_matches_profile
                and (
                    not currentness_sensitive
                    or family_currentness != "historical"
                )
            )
            if force_required and family_reason == "source_inventory":
                family_reason = "surface_matched_family"
                family_score = max(family_score, 30)
            family_pages = list(family.pages)
            if exact_target_page_set:
                family_pages = [page for page in family_pages if page in exact_target_page_set]
            for page in family_pages:
                register(
                    page,
                    score=family_score,
                    entry=(section_map.entries or {}).get(family.chunk_ids[0]) if family.chunk_ids else None,
                    reason=family_reason,
                    authority=family.authority,
                    source_family_ids=[family.family_id],
                    force_required=force_required,
                )

    if not exact_target_page_set:
        for flag in review_flags or []:
            if not isinstance(flag, dict):
                continue
            for page in flag.get("pages", []) or []:
                if isinstance(page, int) or (isinstance(page, str) and str(page).isdigit()):
                    register(
                        int(page),
                        score=25,
                        entry=None,
                        reason="validation_hint_page",
                        authority="supporting",
                    )
            for chunk_id in flag.get("chunk_ids", []) or []:
                clean_chunk_id = _clean_text(chunk_id)
                if not clean_chunk_id:
                    continue
                entry = (getattr(section_map, "entries", {}) or {}).get(clean_chunk_id)
                if entry is None or bool(getattr(entry, "is_noise", False)):
                    continue
                start = getattr(entry, "page_start", None)
                end = getattr(entry, "page_end", None) or start
                if start is None or end is None:
                    continue
                for page in range(int(start), int(end) + 1):
                    register(
                        page,
                        score=28,
                        entry=entry,
                        reason="validation_hint_chunk",
                        authority="authoritative" if _clean_text(getattr(entry, "label", "")) == preferred_label else "supporting",
                    )

    if not restrict_to_target_families:
        chunks = list(getattr(bundle, "chunks", []) or [])
        for rank, (chunk, _score) in enumerate(chunks, start=1):
            entry = section_map.entries.get(str(getattr(chunk, "id", "")))
            if entry is None or bool(getattr(entry, "is_noise", False)):
                continue
            label = _clean_text(getattr(entry, "label", ""))
            source_surface = _clean_text(getattr(entry, "source_surface", ""))
            if preferred_surfaces and source_surface not in preferred_surfaces and label != preferred_label:
                allowed_labels = set(getattr(profile, "allowed_section_labels", []) or [])
                if label not in allowed_labels:
                    continue
            score = _score_entry(
                entry,
                rank=rank,
                preferred_label=preferred_label,
                preferred_surfaces=preferred_surfaces,
            )
            authority = "authoritative" if (label == preferred_label or source_surface in preferred_surfaces) else "supporting"
            start = getattr(entry, "page_start", None)
            end = getattr(entry, "page_end", None) or start
            if start is None or end is None:
                continue
            for page in range(int(start), int(end) + 1):
                register(page, score=score, entry=entry, reason="retrieved_evidence", authority=authority)

    if not page_entries and preferred_label:
        for rank, chunk_id in enumerate(section_map.by_label.get(preferred_label, [])[:48], start=1):
            entry = section_map.entries.get(str(chunk_id))
            if entry is None or bool(getattr(entry, "is_noise", False)):
                continue
            score = _score_entry(
                entry,
                rank=rank,
                preferred_label=preferred_label,
                preferred_surfaces=preferred_surfaces,
            )
            start = getattr(entry, "page_start", None)
            end = getattr(entry, "page_end", None) or start
            if start is None or end is None:
                continue
            for page in range(int(start), int(end) + 1):
                register(page, score=score, entry=entry, reason="section_label_fallback", authority="authoritative")

    if not page_entries:
        return HardPageManifest(profile_name=profile_name)

    ranked_pages = [
        page
        for page, _entry in sorted(
            page_entries.items(),
            key=lambda item: (-item[1].score, item[0]),
        )
    ]
    if exact_target_page_set:
        ranked_pages = [page for page in ranked_pages if page in exact_target_page_set]
    selected_pages: list[int] = []
    selected_set: set[int] = set()
    required_pages = [
        page
        for page, entry in sorted(page_entries.items(), key=lambda item: item[0])
        if entry.required and (not exact_target_page_set or page in exact_target_page_set)
    ]
    for page in required_pages:
        if page in selected_set:
            continue
        selected_pages.append(page)
        selected_set.add(page)
    selection_cap = max(max_pages, len(required_pages))
    if len(selected_pages) < selection_cap:
        for page in ranked_pages:
            if page in selected_set:
                continue
            selected_pages.append(page)
            selected_set.add(page)
            if len(selected_pages) >= selection_cap:
                break

    if spillover_pages > 0 and len(selected_pages) < selection_cap:
        for page in list(selected_pages):
            for delta in range(1, spillover_pages + 1):
                for candidate in (page - delta, page + delta):
                    if candidate <= 0 or candidate in selected_set or (max_page_count and candidate > max_page_count):
                        continue
                    selected_pages.append(candidate)
                    selected_set.add(candidate)
                    register(candidate, score=1, entry=None, reason="continuation_window", authority="supporting")
                    if len(selected_pages) >= selection_cap:
                        break
                if len(selected_pages) >= selection_cap:
                    break
            if len(selected_pages) >= selection_cap:
                break

    ordered_entries = [page_entries[page] for page in sorted(selected_set)]
    manifest = HardPageManifest(
        profile_name=profile_name,
        pages=ordered_entries,
        selection_reasons=list(dict.fromkeys(list(selection_reasons or []) + target_family_ids)),
    )
    manifest.page_families = _build_page_families(
        ordered_entries,
        source_family_lookup=target_family_lookup,
        required_family_ids=required_family_ids,
    )
    return manifest
