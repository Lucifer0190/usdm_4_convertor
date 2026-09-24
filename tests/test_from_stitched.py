"""The StitchedGrid -> SoAGrid bridge (task 2.7): header normalization and
the 3-header-row scope boundary."""
from __future__ import annotations

from usdm4_assure.soa.from_stitched import is_mark, normalize_header, stitched_to_soa_grid
from usdm4_assure.soa.stitch import Segment, StitchedCell, StitchedGrid


def _cell(text):
    return StitchedCell(text, page=1, bbox=None)


def _row(*texts):
    return [_cell(t) for t in texts]


def _segment():
    return Segment(page=1, bbox=None, header_rows_skipped=0, dropped_columns=())


def test_normalize_header_is_a_noop_when_already_confirmed():
    header = [_row("", "V1")]
    body = [_row("Vitals", "X")]
    g = StitchedGrid("pymupdf", [_segment()], header, body, n_header_rows=1)
    assert normalize_header(g) is g


def test_normalize_header_falls_back_when_unconfirmed():
    rows = [_row("", "V1"), _row("Visit", "1"), _row("Day", "1"), _row("Vitals", "X")]
    g = StitchedGrid("pymupdf", [_segment()], [], rows, n_header_rows=None)
    normalized = normalize_header(g)
    assert normalized.n_header_rows == 3
    assert [r[0].text for r in normalized.header] == ["", "Visit", "Day"]
    assert [r[0].text for r in normalized.body] == ["Vitals"]


def test_normalize_header_custom_default():
    rows = [_row("", "V1"), _row("Vitals", "X")]
    g = StitchedGrid("pymupdf", [_segment()], [], rows, n_header_rows=None)
    normalized = normalize_header(g, default_header_rows=1)
    assert normalized.n_header_rows == 1
    assert [r[0].text for r in normalized.body] == ["Vitals"]


def test_stitched_to_soa_grid_unconfirmed_single_page_defaults_to_three():
    rows = [_row("", "Screening", "Treatment"), _row("Visit", "V1", "V2"),
           _row("Day", "1", "8"), _row("Vitals", "X", "")]
    g = StitchedGrid("pymupdf", [_segment()], [], rows, n_header_rows=None)
    sg = stitched_to_soa_grid(g)
    assert sg is not None
    assert sg.epochs == ["Screening", "Treatment"]
    assert sg.visits == ["V1", "V2"] and sg.timings == ["1", "8"]
    assert sg.activities == ["Vitals"] and sg.cells == {(0, 0)}


def test_stitched_to_soa_grid_confirmed_non_three_header_is_none():
    header = [_row("", "V1")]  # confirmed via repetition, but only 1 header row
    body = [_row("Vitals", "X")]
    g = StitchedGrid("pymupdf", [_segment(), _segment()], header, body, n_header_rows=1)
    assert stitched_to_soa_grid(g) is None


def test_footnote_marker_is_stripped_and_recorded():
    rows = [_row("", "V1"), _row("Visit", "1"), _row("Day", "1"), _row("PK Sample a", "X")]
    g = StitchedGrid("pymupdf", [_segment()], [], rows, n_header_rows=None)
    sg = stitched_to_soa_grid(g)
    assert sg.activities == ["PK Sample"]
    assert sg.footnote_activities == {"PK Sample"}


def test_epoch_row_is_forward_filled_across_spanned_cells():
    rows = [_row("", "Screening", "", ""), _row("Visit", "V1", "V2", "V3"),
           _row("Day", "1", "8", "15"), _row("Vitals", "X", "", "")]
    g = StitchedGrid("pymupdf", [_segment()], [], rows, n_header_rows=None)
    sg = stitched_to_soa_grid(g)
    assert sg.epochs == ["Screening", "Screening", "Screening"]


def test_is_mark_recognizes_the_usual_glyphs_and_rejects_prose():
    assert is_mark("X") and is_mark("✓") and is_mark("●")
    assert not is_mark("") and not is_mark(None)
    assert not is_mark("As clinically indicated")
