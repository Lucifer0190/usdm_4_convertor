"""Evidence windows (task 3.5, L3) — prohibited-scope filtering per domain.

Every extractor reads a :class:`~usdm4_assure.contracts.Document`; a window is
the same document with the blocks of prohibited sections removed, so the
extractors (deterministic and two-pass LLM alike) need no change to be scoped.

Two layers of prohibition, both matched with the reference extractor's
semantics (a scope matches when *every* axis it names matches — AND across
axes, any-of within an axis):

1. the route's own ``prohibited_scopes`` from the ported planner;
2. a **currentness guard** we add for every domain except ``amendments``:
   ``amendment_history`` sections and historic SoA / amendment surfaces never
   feed current-design evidence.

Layer 2 is not redundant. The ported planner's historic prohibitions name a
``source_surfaces`` axis (``schedule_table_historic``) that our section graph
does not populate, so under AND semantics they never fire here — without the
guard an amendment-history passage stating the *old* arm count would reach the
design extractor (``tests/test_scope_leak.py`` demonstrates exactly that).

Blocks before the first detected section (title page, unlabelled front
matter) are kept: they cannot be scoped, and the title page is where study
identity lives. Every filtered section becomes a ``SCOPE`` :class:`Finding`,
and the window carries the plan hash for the audit trail.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from usdm4_assure.contracts import (
    BBox,
    Document,
    Finding,
    FindingKind,
    GroundedCandidate,
    Severity,
)
from usdm4_assure.sections.graph import Section
from usdm4_assure.sections.models import RouteScopePlan
from usdm4_assure.sections.plan import DOMAIN_ROUTES, RoutedDocument

HISTORIC_GUARD: list[RouteScopePlan] = [
    RouteScopePlan(section_subtypes=["amendment_history"]),
    RouteScopePlan(authority_surfaces=["soa_table_historic", "amendment_table",
                                       "amendment_summary"]),
]
_GUARD_EXEMPT_ROUTES = frozenset({"amendments"})

# Values the reference assigns to axes our graph does not populate; used so a
# scope naming one of those axes behaves exactly as it would there.
_UNPOPULATED = {"source_surfaces": "", "table_roles": "", "study_scopes": "main_study",
                "phase_scopes": "all", "arm_scopes": "all_arms", "region_scopes": "all_regions"}


def scope_matches(section: Section, scope: RouteScopePlan) -> bool:
    """Reference semantics: every non-empty axis of ``scope`` must contain the section's value."""
    values = {"section_types": section.section_type,
              "section_subtypes": section.section_subtype,
              "authority_surfaces": section.authority_surface, **_UNPOPULATED}
    for axis, section_value in values.items():
        allowed = getattr(scope, axis)
        if allowed and section_value not in allowed:
            return False
    return any(getattr(scope, axis) for axis in values)   # an empty scope matches nothing


def _prohibiting_scope(section: Section, scopes: list[RouteScopePlan]) -> RouteScopePlan | None:
    return next((s for s in scopes if scope_matches(section, s)), None)


def _describe(scope: RouteScopePlan) -> str:
    return "; ".join(f"{k}={v}" for k, v in scope.to_dict().items() if v)


@dataclass
class EvidenceWindow:
    """One domain's scoped view of the document."""
    domain: str
    route: str | None
    document: Document
    plan_hash: str | None
    prohibited_sections: list[Section] = field(default_factory=list)
    blocks_kept: int = 0
    blocks_dropped: int = 0
    findings: list[Finding] = field(default_factory=list)
    _routed: RoutedDocument | None = None

    def is_prohibited(self, page: int, y: float = 0.0) -> bool:
        if self._routed is None:
            return False
        section = self._routed.graph.section_for(page, y)
        return section is not None and section in self.prohibited_sections

    def retrieval_config(self) -> dict:
        """The ``AuditRecord.retrieval_config`` payload for fields from this window."""
        return {"domain": self.domain, "route": self.route, "route_plan_hash": self.plan_hash,
                "blocks_kept": self.blocks_kept, "blocks_dropped": self.blocks_dropped,
                "prohibited_sections": [s.title for s in self.prohibited_sections]}


def window_for(doc: Document, routed: RoutedDocument | None, domain: str) -> EvidenceWindow:
    """Filter ``doc`` down to what ``domain`` may use as evidence.

    ``routed is None`` (routing disabled) returns the whole document unfiltered,
    with no plan hash — the routing-off arm of the Phase 3 comparison.
    """
    if routed is None:
        return EvidenceWindow(domain, None, doc, None, blocks_kept=len(doc.blocks))
    route = routed.route_for(domain)
    route_name = DOMAIN_ROUTES.get(domain)
    scopes = list(route.prohibited_scopes) if route else []
    if route_name not in _GUARD_EXEMPT_ROUTES:
        scopes += HISTORIC_GUARD

    findings: list[Finding] = []
    if not routed.graph.sections:
        findings.append(Finding(
            FindingKind.SCOPE, Severity.WARNING, domain,
            "No section graph could be built; evidence for this domain is unscoped "
            "(prohibited scopes cannot be enforced)."))

    prohibited: dict[int, tuple[Section, RouteScopePlan]] = {}
    for i, s in enumerate(routed.graph.sections):
        scope = _prohibiting_scope(s, scopes)
        if scope is not None:
            prohibited[i] = (s, scope)
    index = {id(s): i for i, s in enumerate(routed.graph.sections)}

    kept: list = []
    dropped_per: dict[int, int] = {}
    for b in doc.blocks:
        sec = routed.graph.block_section(b)
        i = index.get(id(sec)) if sec is not None else None
        if i is not None and i in prohibited:
            dropped_per[i] = dropped_per.get(i, 0) + 1
        else:
            kept.append(b)

    for i, n in dropped_per.items():
        s, scope = prohibited[i]
        findings.append(Finding(
            FindingKind.SCOPE, Severity.INFO, domain,
            f"Filtered {n} block(s) of section '{s.title}' (p{s.page}) from {domain} evidence: "
            f"prohibited by {route_name or 'currentness guard'} scope [{_describe(scope)}].",
            expected="excluded", found=s.section_subtype or s.section_type))

    scoped = Document(source=doc.source, blocks=kept,
                      full_text="\n".join(b.text for b in kept),
                      page_images=doc.page_images, chars=doc.chars)
    return EvidenceWindow(domain, route_name, scoped, routed.plan_hash,
                          prohibited_sections=[s for s, _ in prohibited.values()],
                          blocks_kept=len(kept), blocks_dropped=len(doc.blocks) - len(kept),
                          findings=findings, _routed=routed)


def _quote_anchor(c: GroundedCandidate) -> tuple[int, BBox] | None:
    if c.quote is None or not c.quote.ok or c.page is None or c.bbox is None:
        return None
    return c.page, c.bbox


def drop_prohibited(cands: list[GroundedCandidate], window: EvidenceWindow
                    ) -> tuple[list[GroundedCandidate], list[Finding]]:
    """Second line of defence: a grounded quote that resolves *inside* a
    prohibited section is dropped, with a WARNING finding.

    The window already keeps prohibited text away from the model; this
    catches the residual case where a quote the model produced still
    matches historic text verbatim (the resolver searches whole pages).
    """
    kept, findings = [], []
    for c in cands:
        anchor = _quote_anchor(c)
        if anchor and window.is_prohibited(anchor[0], anchor[1][1]):
            findings.append(Finding(
                FindingKind.SCOPE, Severity.WARNING, window.domain,
                f"Dropped candidate for {c.field}: its quote resolves inside a prohibited "
                f"section on page {anchor[0]}.", field=c.field, found=c.value))
        else:
            kept.append(c)
    return kept, findings
