"""Prohibited-scope filtering of evidence windows (task 3.5).

The documented leak: a protocol whose front-matter amendment summary quotes
the ORIGINAL design ("randomized 1:1:1 to one of 3 arms") ahead of the current
design section ("1:1 to one of 2 arms"). The design extractor takes the first
arm enumeration it sees, so without routing the superseded 3-arm design leaks
into the study; with routing the amendment section is filtered from the design
window and the current 2-arm design is extracted.

Run on both graph sources: numbered/unnumbered headings only (no outline) and
a PDF outline.
"""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from usdm4_assure.contracts import (
    Block,
    Document,
    FindingKind,
    GroundedCandidate,
    Method,
    Quote,
    Severity,
    VerifyPass,
)
from usdm4_assure.extract.design import extract_design
from usdm4_assure.extract.windows import (
    HISTORIC_GUARD,
    drop_prohibited,
    scope_matches,
    window_for,
)
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.llm.router import get_llm
from usdm4_assure.sections.classify import classify_title
from usdm4_assure.sections.graph import Section
from usdm4_assure.sections.models import RouteScopePlan
from usdm4_assure.sections.plan import build_plan

OLD_ARMS = ("Original protocol (version 1.0): participants were randomized 1:1:1 to one of "
            "3 arms: Drug A Low Dose, Drug A High Dose, or Placebo.")
NEW_ARMS = ("In this amended protocol participants are randomized 1:1 to one of 2 arms: "
            "Drug A or Placebo.")

PAGES = [
    [("Clinical Study Protocol", 18), ("A Phase 3, Randomized Study of Drug A in Adults", 12),
     ("Protocol DA-301 Version 2.0", 10)],
    [("PROTOCOL AMENDMENT SUMMARY OF CHANGES", 16), (OLD_ARMS, 10),
     ("Amendment 1 reduced the number of dose levels.", 10)],
    [("4 STUDY DESIGN", 16), ("4.1 Overall Design", 12), (NEW_ARMS, 10),
     ("The study is a parallel group design.", 10)],
    [("5 STUDY POPULATION", 16), ("5.1 Inclusion Criteria", 12),
     ("Adults aged 18 to 75 years at screening.", 10)],
]
TOC = [[1, "PROTOCOL AMENDMENT SUMMARY OF CHANGES", 2], [1, "4 STUDY DESIGN", 3],
       [2, "4.1 Overall Design", 3], [1, "5 STUDY POPULATION", 4],
       [2, "5.1 Inclusion Criteria", 4]]


def _protocol(path: Path, bookmarks: bool) -> Path:
    pdf = pymupdf.open()
    for lines in PAGES:
        page = pdf.new_page()
        y = 80
        for text, size in lines:
            page.insert_textbox(pymupdf.Rect(72, y, 540, y + 60), text, fontsize=size)
            y += 70
    if bookmarks:
        pdf.set_toc(TOC)
    pdf.save(path)
    pdf.close()
    return path


@pytest.fixture(params=["headings", "bookmarks"])
def protocol(request, tmp_path):
    pdf = _protocol(tmp_path / f"amended_{request.param}.pdf", request.param == "bookmarks")
    doc = ingest(pdf)
    return pdf, doc, build_plan(doc, pdf)


def _arm_names(doc: Document) -> list[str]:
    _, design = extract_design(doc, {}, get_llm())
    return [a["name"] for a in design.arms]


# --- the leak ------------------------------------------------------------------ #
def test_without_routing_old_arm_count_leaks(protocol):
    _, doc, _ = protocol
    # Proves the fixture is a real trap: the unscoped extractor takes the old design.
    assert len(_arm_names(doc)) == 3


def test_with_routing_old_arm_count_does_not_leak(protocol):
    pdf, doc, routed = protocol
    assert routed.graph.source == ("bookmark" if "bookmarks" in pdf.name else "heading")
    win = window_for(doc, routed, "design")
    assert "1:1:1" not in win.document.full_text
    assert NEW_ARMS.split(":")[0] in win.document.full_text
    assert _arm_names(win.document) == ["Drug A", "Placebo"]


def test_filtered_section_is_a_scope_finding(protocol):
    _, doc, routed = protocol
    win = window_for(doc, routed, "design")
    scope = [f for f in win.findings if f.kind is FindingKind.SCOPE]
    assert len(scope) == 1
    assert "PROTOCOL AMENDMENT SUMMARY OF CHANGES" in scope[0].message
    assert scope[0].found == "amendment_history"
    assert win.blocks_dropped >= 2


def test_current_sections_stay_in_every_current_domain(protocol):
    _, doc, routed = protocol
    for domain in ("metadata", "design", "eligibility", "objectives"):
        text = window_for(doc, routed, domain).document.full_text
        assert "1:1:1" not in text
        assert "Clinical Study Protocol" in text     # front matter is never filtered


# --- why the guard is needed ---------------------------------------------------- #
def _section(title: str) -> Section:
    return Section(title, "", 1, 2, 80, "heading", classify_title(title), "rule")


def test_ported_design_route_alone_would_not_block_amendment_history(protocol):
    _, _, routed = protocol
    amend = _section("PROTOCOL AMENDMENT SUMMARY OF CHANGES")
    route = routed.route_for("design")
    # AND semantics + a source_surfaces axis our graph never populates.
    assert not any(scope_matches(amend, s) for s in route.prohibited_scopes)
    assert any(scope_matches(amend, s) for s in HISTORIC_GUARD)


def test_scope_matching_is_and_across_axes_any_within():
    appendix = _section("Appendix 3 Clinical Laboratory Tests")
    assert scope_matches(appendix, RouteScopePlan(section_types=["appendix", "summary"]))
    assert not scope_matches(appendix, RouteScopePlan(section_types=["appendix"],
                                                      source_surfaces=["appendix_operational"]))
    assert not scope_matches(appendix, RouteScopePlan())      # empty scope matches nothing


def test_historic_soa_is_guarded():
    amend = classify_title("Appendix 10.9 Protocol Amendment History")
    historic = Section("Schedule of Activities", "", 2, 90, 80, "bookmark",
                       classify_title("Schedule of Activities"), "rule")
    from usdm4_assure.sections.classify import resolve
    historic = Section(historic.title, "", 2, 90, 80, "bookmark",
                       resolve(historic.labels, amend), "rule")
    assert historic.authority_surface == "soa_table_historic"
    assert any(scope_matches(historic, s) for s in HISTORIC_GUARD)


# --- window plumbing -------------------------------------------------------------- #
def test_routing_off_is_the_whole_document(protocol):
    _, doc, _ = protocol
    win = window_for(doc, None, "design")
    assert win.document is doc and win.plan_hash is None and win.findings == []


def test_retrieval_config_carries_route_plan_hash(protocol):
    _, doc, routed = protocol
    cfg = window_for(doc, routed, "design").retrieval_config()
    assert cfg["route_plan_hash"] == routed.plan_hash
    assert cfg["route"] == "design_structure"
    assert cfg["prohibited_sections"] == ["PROTOCOL AMENDMENT SUMMARY OF CHANGES"]
    json.dumps(cfg)                                    # audit stores it as JSON


def test_quote_resolving_inside_prohibited_section_is_dropped(protocol):
    _, doc, routed = protocol
    win = window_for(doc, routed, "design")
    amend_block = next(b for b in doc.blocks if "1:1:1" in b.text)
    design_block = next(b for b in doc.blocks if "1:1 to one of 2" in b.text)

    def cand(block: Block) -> GroundedCandidate:
        return GroundedCandidate("interventionModel", "Parallel", Method.LLM_FRONTIER,
                                 Quote(block.text[:40], VerifyPass.EXACT, block.page,
                                       0, 40, block.bbox))

    kept, findings = drop_prohibited([cand(amend_block), cand(design_block)], win)
    assert [c.page for c in kept] == [design_block.page]
    assert findings[0].severity is Severity.WARNING and findings[0].field == "interventionModel"


def test_no_section_graph_is_flagged_not_silent(tmp_path):
    doc = Document(source=Path("flat.pdf"),
                   blocks=[Block("randomized 1:1 to one of 2 arms: A or B.", 1, (0, 0, 1, 1))],
                   full_text="randomized 1:1 to one of 2 arms: A or B.")
    win = window_for(doc, build_plan(doc), "design")
    assert win.blocks_dropped == 0
    assert any(f.severity is Severity.WARNING and "unscoped" in f.message for f in win.findings)
