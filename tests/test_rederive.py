"""Mechanical mark-matrix re-derivation (task 2.6): glyph geometry vs. claimed marks.

Three layers, matching test_stitch.py's convention:
* the five hand-labelled usdm_data SoAs (skipped when the gitignored corpus
  under spikes/_work/ is absent) — rederived marks vs. extraction's own
  claimed marks, the comparison this module actually makes;
* the synthetic reportlab SoA fixture, end to end through ingest + stitch;
* synthetic in-memory ``Document``/``CharSpan`` geometry, pinning bbox-membership.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_soa_fixture import build

from usdm4_assure.contracts import CharSpan, Document
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.layout.pymupdf_adapter import extract_tables
from usdm4_assure.soa.corrections import read_corrections, write_corrections
from usdm4_assure.soa.rederive import (
    as_findings,
    disagreements,
    glyphs_in_bbox,
    rederive_grid,
    rederive_mark,
)
from usdm4_assure.soa.stitch import Segment, StitchedCell, StitchedGrid, stitch

ROOT = Path(__file__).resolve().parents[1]
LABELS = sorted((ROOT / "data" / "labels" / "soa").glob("*.json"))


# --- real labelled SoAs -------------------------------------------------------- #
# Rederivation checks agreement between two independent reads of "does this
# cell contain a mark glyph" -- extraction's own claimed text vs. glyph
# geometry -- not against the label's ground truth. Some labelled SoAs record
# "activity performed" via free-text scheduling detail rather than an X/checkmark
# glyph (e.g. "Pre-hypoglycemia induction, 90 min"); `is_mark()` correctly
# reports no glyph mark there on *both* reads, so claimed and rederived agree
# with each other even though neither matches the label's broader notion of
# "marked". Redefining what counts as a mark for such protocols is out of this
# module's scope (from_stitched.py owns that convention).
@pytest.mark.parametrize("label_path", LABELS, ids=[p.stem for p in LABELS])
def test_rederived_marks_agree_with_extractions_own_claim(label_path):
    lab = json.loads(label_path.read_text(encoding="utf-8"))
    pdf = ROOT / lab["source_pdf"]
    if not pdf.exists():
        pytest.skip(f"usdm_data corpus not present ({pdf.name})")
    pages = lab["pages"]
    window = range(max(1, pages[0] - 2), pages[-1] + 3)
    res = stitch(extract_tables(pdf, window))
    matches = [g for g in res.grids if g.pages == pages]
    assert matches, f"no stitched grid spans exactly {pages}: {[g.pages for g in res.grids]}"
    g = matches[0]
    doc = ingest(pdf)

    comparisons = rederive_grid(doc, g)
    assert comparisons
    agree = sum(c.agree for c in comparisons)
    assert agree / len(comparisons) >= 0.95


# --- synthetic reportlab fixture, end to end ----------------------------------- #
def test_rederive_agrees_with_claimed_marks_on_the_synthetic_fixture():
    pdf = build()
    doc = ingest(pdf)
    g = stitch(extract_tables(pdf)).grids[0]
    comparisons = rederive_grid(doc, g)
    assert comparisons
    assert disagreements(comparisons) == []


def test_as_findings_is_empty_when_everything_agrees():
    pdf = build()
    doc = ingest(pdf)
    g = stitch(extract_tables(pdf)).grids[0]
    assert as_findings(rederive_grid(doc, g)) == []


# --- synthetic in-memory geometry ---------------------------------------------- #
def _doc_with_chars(page: int, chars: list[CharSpan]) -> Document:
    return Document(source=Path("x.pdf"), blocks=[], full_text="", chars={page: chars})


def test_glyphs_in_bbox_returns_only_characters_whose_centre_is_inside():
    chars = [
        CharSpan("X", 1, (10.0, 10.0, 15.0, 15.0)),   # centre (12.5, 12.5) -> inside
        CharSpan("Y", 1, (100.0, 100.0, 105.0, 105.0)),  # outside
    ]
    doc = _doc_with_chars(1, chars)
    assert glyphs_in_bbox(doc, 1, (0.0, 0.0, 20.0, 20.0)) == "X"


def test_rederive_mark_true_for_a_mark_glyph_in_the_bbox():
    doc = _doc_with_chars(1, [CharSpan("✓", 1, (10.0, 10.0, 15.0, 15.0))])
    assert rederive_mark(doc, 1, (0.0, 0.0, 20.0, 20.0)) is True


def test_rederive_mark_false_when_no_glyph_or_wrong_page():
    doc = _doc_with_chars(1, [CharSpan("X", 1, (10.0, 10.0, 15.0, 15.0))])
    assert rederive_mark(doc, 1, (0.0, 0.0, 5.0, 5.0)) is False
    assert rederive_mark(doc, 2, (0.0, 0.0, 20.0, 20.0)) is False


def _cell(text, bbox=None, page=1):
    return StitchedCell(text, page=page, bbox=bbox)


def test_rederive_grid_flags_a_claimed_mark_the_glyphs_do_not_back_up():
    header = [
        [_cell(""), _cell("Screening")],
        [_cell("Visit"), _cell("V1")],
        [_cell("Day"), _cell("1")],
    ]
    body = [[_cell("Vitals"), _cell("X", bbox=(0.0, 0.0, 20.0, 20.0))]]
    seg = Segment(page=1, bbox=None, header_rows_skipped=0, dropped_columns=())
    g = StitchedGrid("pymupdf", [seg], header, body, n_header_rows=3)
    # No glyphs anywhere near the claimed cell -- rederivation says blank.
    doc = _doc_with_chars(1, [])
    comparisons = rederive_grid(doc, g)
    assert len(comparisons) == 1
    c = comparisons[0]
    assert c.claimed is True and c.rederived is False and c.agree is False
    findings = as_findings(comparisons)
    assert len(findings) == 1 and findings[0].field == "Vitals"


def test_rederive_grid_cell_without_bbox_is_reported_as_agreeing():
    header = [[_cell(""), _cell("Screening")], [_cell("Visit"), _cell("V1")],
             [_cell("Day"), _cell("1")]]
    body = [[_cell("Vitals"), _cell("X", bbox=None)]]
    seg = Segment(page=1, bbox=None, header_rows_skipped=0, dropped_columns=())
    g = StitchedGrid("pymupdf", [seg], header, body, n_header_rows=3)
    doc = _doc_with_chars(1, [])
    comparisons = rederive_grid(doc, g)
    assert comparisons[0].agree is True


# --- corrections sidecar -------------------------------------------------------- #
def test_write_and_read_corrections_round_trips(tmp_path):
    header = [[_cell(""), _cell("Screening")], [_cell("Visit"), _cell("V1")],
             [_cell("Day"), _cell("1")]]
    body = [[_cell("Vitals"), _cell("X", bbox=(0.0, 0.0, 20.0, 20.0))]]
    seg = Segment(page=1, bbox=None, header_rows_skipped=0, dropped_columns=())
    g = StitchedGrid("pymupdf", [seg], header, body, n_header_rows=3)
    doc = _doc_with_chars(1, [])
    comparisons = rederive_grid(doc, g)

    path = tmp_path / "corrections.json"
    write_corrections(path, "protocol.pdf", comparisons)
    got = read_corrections(path, "protocol.pdf")
    assert len(got) == 1
    assert got[0]["activity"] == "Vitals" and got[0]["claimed"] is True and got[0]["rederived"] is False


def test_write_corrections_does_not_drop_a_different_pdfs_entry(tmp_path):
    path = tmp_path / "corrections.json"
    write_corrections(path, "a.pdf", [])
    write_corrections(path, "b.pdf", [])
    data = json.loads(path.read_text())
    assert set(data) == {str(Path("a.pdf")), str(Path("b.pdf"))}


def test_read_corrections_returns_empty_list_for_a_pdf_never_written():
    assert read_corrections(Path("does-not-exist.json"), "x.pdf") == []
