"""Section graph, fingerprint and route plan (task 3.4).

Covers only our code — the ported route planner is exercised through
``build_plan`` but not asserted on beyond "a plan comes back". Three layers:
title classification, synthetic heading/bookmark graphs, and three real
usdm_data protocols (skipped when the gitignored corpus is absent): one with a
PDF outline, two without.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from usdm4_assure.contracts import Block, Document
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.sections.classify import classify_title, resolve, taxonomy
from usdm4_assure.sections.fingerprint import (
    DEFAULT_CONFIDENCE,
    DETECTED_CONFIDENCE,
    families,
    fingerprint,
)
from usdm4_assure.sections.graph import (
    Section,
    SectionGraph,
    build_graph,
    classify_residue,
    from_headings,
)
from usdm4_assure.sections.plan import DOMAIN_ROUTES, build_plan, plan_hash

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "spikes" / "_work" / "usdm_data" / "source_data" / "protocols"


def _doc(*blocks: tuple[int, float, str, str]) -> Document:
    """``(page, y, text, kind)`` tuples → a block-only Document."""
    bl = [Block(text=t, page=p, bbox=(72.0, y, 500.0, y + 12), kind=k) for p, y, t, k in blocks]
    return Document(source=Path("synthetic.pdf"), blocks=bl, full_text="\n".join(b.text for b in bl))


# --- classification ------------------------------------------------------------ #
@pytest.mark.parametrize("title,stype,subtype", [
    ("5.1 Inclusion Criteria", "population", None),
    ("1.3 Schedule of Activities (SoA)", "assessments", "soa_main"),
    ("2 Flowchart", "assessments", "soa_main"),
    ("3. Objectives and Endpoints", "science", "objectives_table"),
    ("9.2 Sample Size Determination", "statistics", "sample_size"),
    ("7.1 Discontinuation of Study Treatment", "disposition", None),
    ("6.1 Study Intervention(s) Administered", "interventions", None),
    ("Protocol Amendment Summary of Changes Table", "summary", "amendment_history"),
    ("Table of Contents", "header", "table_of_contents"),
    ("Appendix 2 Clinical Laboratory Tests", "appendix", None),
])
def test_classify_title(title, stype, subtype):
    labels = classify_title(title)
    assert labels.section_type == stype
    assert labels.section_subtype == subtype


def test_classify_is_template_independent_of_numbering():
    # Lilly's older template: "5." is Introduction, not Population (ICH M11).
    assert classify_title("5. Introduction").section_type == "introduction"


def test_unknown_title_is_untyped():
    assert not classify_title("Miscellaneous Notes").typed


def test_every_emitted_label_is_in_the_taxonomy():
    tax = taxonomy()
    for title in ["5.1 Inclusion Criteria", "1.3 Schedule of Activities", "Estimands",
                  "Abbreviations", "Title Page", "Interim Analysis", "Response Criteria"]:
        lab = classify_title(title)
        assert lab.section_type in tax["canonical_section_type"]
        assert lab.section_subtype in (None, *tax["section_subtype"])
        assert lab.authority_surface in tax["authority_surface"]


def test_resolve_inherits_when_child_has_no_signal():
    parent = classify_title("5 Study Population")
    assert resolve(classify_title("5.3 Miscellaneous"), parent) == parent


def test_resolve_appendix_is_sticky():
    child = resolve(classify_title("Clinical Laboratory Tests"), classify_title("Appendix 2"))
    assert child.section_type == "appendix"
    assert child.section_subtype == "lab_inventory"


def test_resolve_summary_is_not_sticky():
    # ICH M11: the SoA sits at 1.3 under "1 Protocol Summary".
    child = resolve(classify_title("1.3 Schedule of Activities"), classify_title("1 Protocol Summary"))
    assert child.section_type == "assessments"
    assert child.authority_surface == "soa_table_current"


def test_resolve_soa_under_amendment_history_is_historic():
    amend = classify_title("Appendix 10.9 Protocol Amendment History")
    child = resolve(classify_title("Schedule of Activities"), amend)
    assert child.section_subtype == "amendment_history"
    assert child.authority_surface == "soa_table_historic"


# --- heading-sourced graph ------------------------------------------------------ #
def test_headings_build_levels_and_inheritance():
    doc = _doc((3, 80, "5 STUDY POPULATION", "heading"),
               (3, 200, "5.1 Inclusion Criteria", "prose"),
               (3, 260, "Participants are eligible if all of the following apply.", "prose"),
               (4, 80, "5.2 Other Considerations", "prose"),
               (5, 80, "6 STUDY INTERVENTION", "heading"))
    g = build_graph(doc)
    assert g.source == "heading"
    assert [s.number for s in g.sections] == ["5", "5.1", "5.2", "6"]
    assert [s.level for s in g.sections] == [1, 2, 2, 1]
    other = g.sections[2]
    assert other.section_type == "population" and other.typed_by == "inherited"
    assert g.sections[3].section_type == "interventions"


def test_section_for_returns_innermost_open_section():
    doc = _doc((3, 80, "5 STUDY POPULATION", "heading"),
               (3, 200, "5.1 Inclusion Criteria", "prose"),
               (5, 80, "6 STUDY INTERVENTION", "heading"))
    g = build_graph(doc)
    assert g.section_for(3, 100).number == "5"
    assert g.section_for(3, 300).number == "5.1"
    assert g.section_for(4, 500).number == "5.1"
    assert g.section_for(5, 90).number == "6"
    assert g.section_for(1, 50) is None     # front matter before any heading


def test_toc_page_entries_are_dropped():
    toc = [(2, 100 + 20 * i, f"{i} Chapter Title {i}", "prose") for i in range(1, 8)]
    doc = _doc(*toc, (5, 80, "1 INTRODUCTION", "heading"))
    assert [s.title for s in from_headings(doc)] == ["1 INTRODUCTION"]


def test_numbered_list_items_are_not_headings():
    doc = _doc((3, 80, "3 PATIENT SELECTION", "heading"),
               (3, 120, "3.1 Inclusion Criteria", "prose"),
               # restarts at 1 inside 3.1 -> goes backwards at body font
               (3, 160, "1 Provision of informed consent", "prose"),
               # steps forward but no "4.x" follows -> a list item
               (3, 200, "4 Documented BRCA mutation status", "prose"),
               # sentence-shaped amendment bullet
               (3, 240, "5 Section 1.4 Study Design: text updated for clarity.", "prose"),
               (4, 80, "3.2 Exclusion Criteria", "prose"))
    assert [s.number for s in from_headings(doc)] == ["3", "3.1", "3.2"]


def test_body_font_chapter_with_subsection_is_kept():
    doc = _doc((10, 80, "2. Introduction", "prose"), (10, 120, "2.1. Study Rationale", "prose"))
    assert [s.number for s in from_headings(doc)] == ["2", "2.1"]


# --- bookmark-sourced graph ----------------------------------------------------- #
def _bookmarked_pdf(path: Path) -> Path:
    pdf = pymupdf.open()
    titles = ["Title Page", "Table of Contents", "1 Protocol Summary", "5 Study Population",
              "Appendix 1 Protocol Amendment History"]
    for t in titles:
        pdf.new_page().insert_text((72, 90), t, fontsize=16)
    pdf.set_toc([[1, "Title Page", 1], [1, "Table of Contents", 2],
                 [1, "1 Protocol Summary", 3], [2, "1.3 Schedule of Activities", 3],
                 [1, "5 Study Population", 4], [2, "5.1 Inclusion Criteria", 4],
                 [1, "Appendix 1 Protocol Amendment History", 5],
                 [2, "Schedule of Activities (Amendment 1)", 5]])
    pdf.save(path)
    pdf.close()
    return path


def test_bookmarks_preferred_and_positioned(tmp_path):
    pdf = _bookmarked_pdf(tmp_path / "bm.pdf")
    g = build_graph(ingest(pdf), pdf)
    assert g.source == "bookmark"
    by_title = {s.title: s for s in g.sections}
    assert by_title["5 Study Population"].y > 0          # located on its heading block
    assert by_title["5.1 Inclusion Criteria"].section_type == "population"
    assert by_title["1.3 Schedule of Activities"].authority_surface == "soa_table_current"
    old = by_title["Schedule of Activities (Amendment 1)"]
    assert old.section_type == "appendix"
    assert old.authority_surface == "soa_table_historic"


# --- route-role residue --------------------------------------------------------- #
class _StubLLM:
    available = True
    name = "stub"

    def __init__(self, answer: str):
        self.answer, self.calls = answer, []

    def complete(self, prompt, *, task="extract_prose", system=None, max_tokens=1024):
        self.calls.append(prompt)
        return self.answer


def _graph_with_residue() -> SectionGraph:
    return SectionGraph([
        Section("5 Study Population", "5", 1, 3, 80, "heading",
                classify_title("5 Study Population"), "rule"),
        Section("9 Miscellaneous", "9", 1, 9, 80, "heading"),
    ], "heading")


def test_route_role_called_only_for_untyped_residue():
    llm = _StubLLM("disposition")
    g = classify_residue(_graph_with_residue(), llm)
    assert len(llm.calls) == 1 and "9 Miscellaneous" in llm.calls[0]
    assert g.sections[1].section_type == "disposition" and g.sections[1].typed_by == "route"
    assert g.sections[0].typed_by == "rule"


def test_route_role_answer_outside_taxonomy_is_rejected():
    g = classify_residue(_graph_with_residue(), _StubLLM("administrative stuff"))
    assert not g.sections[1].labels.typed


def test_route_role_skipped_when_unavailable():
    llm = _StubLLM("design")
    llm.available = False
    classify_residue(_graph_with_residue(), llm)
    assert llm.calls == []


# --- fingerprint ----------------------------------------------------------------- #
def test_family_yaml_default_first_and_keys_unique():
    fams = families()
    assert fams[0].key == "standard_randomized_phase3" and not fams[0].match
    assert len({f.key for f in fams}) == len(fams)


def test_fingerprint_detects_family_from_title():
    doc = _doc((1, 80, "A Phase 1b/2 Open-Label Study of XYZ-1 in Solid Tumours", "heading"))
    fp = fingerprint(doc, build_graph(doc))
    assert fp.study_archetype == "phase1b_phase2_split"
    assert fp.multi_part_study and fp.confidence == DETECTED_CONFIDENCE
    assert {"phase_1b", "phase_2"} <= set(fp.phase_structure)


def test_fingerprint_default_is_flagged_as_default():
    doc = _doc((1, 80, "A Randomized Study of ABC in Psoriasis", "heading"))
    fp = fingerprint(doc, build_graph(doc))
    assert fp.study_archetype == "standard_randomized_phase3"
    assert fp.confidence == DEFAULT_CONFIDENCE
    assert "defaulted" in fp.rationale[0].lower()


def test_fingerprint_tags_amendment_appendix(tmp_path):
    pdf = _bookmarked_pdf(tmp_path / "bm.pdf")
    doc = ingest(pdf)
    assert "historical_amendment_appendix" in fingerprint(doc, build_graph(doc, pdf)).adaptation_tags


# --- plan --------------------------------------------------------------------------- #
def test_plan_routes_every_domain_and_hash_is_stable(tmp_path):
    pdf = _bookmarked_pdf(tmp_path / "bm.pdf")
    doc = ingest(pdf)
    a, b = build_plan(doc, pdf), build_plan(doc, pdf)
    assert a.plan_hash == b.plan_hash == plan_hash(a.plan)
    for domain in DOMAIN_ROUTES:
        assert a.route_for(domain) is not None
    assert a.route_for("unknown") is None


# --- real protocols ------------------------------------------------------------------ #
REAL = {
    # file: (expected graph source, SoA heading expected to be found)
    "Alexion_NCT04573309_Wilsons/Alexion_NCT04573309_Wilsons.pdf": ("bookmark", True),
    "AZ_NCT03402841_Oncology/AZ_NCT03402841_Oncology.pdf": ("heading", True),
    "CDISC_Pilot/CDISC_Pilot_Study.pdf": ("heading", False),
}


@pytest.mark.parametrize("rel", sorted(REAL))
def test_real_protocol_graph(rel):
    pdf = CORPUS / rel
    if not pdf.exists():
        pytest.skip("usdm_data corpus not present (spikes/_work is gitignored)")
    source, has_soa = REAL[rel]
    routed = build_plan(ingest(pdf), pdf)
    g = routed.graph
    assert g.source == source
    assert len(g.sections) >= 40
    assert g.typed_fraction >= 0.85
    types = {s.section_type for s in g.sections}
    assert {"population", "design", "science", "statistics"} <= types
    assert any(s.section_subtype == "soa_main" for s in g.sections) == has_soa
    assert set(DOMAIN_ROUTES.values()) <= set(routed.plan.domain_routes)
