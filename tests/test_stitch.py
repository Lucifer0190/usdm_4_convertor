"""Multi-page SoA stitcher: real labelled SoAs reproduce, and ambiguity is loud.

Three layers:
* the five hand-labelled usdm_data SoAs (skipped when the gitignored corpus
  under spikes/_work/ is absent, e.g. in CI);
* a synthetic multi-page reportlab table, end to end through PyMuPDF (always runs);
* in-memory grids pinning each continuation rule, including every ambiguous case.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from usdm4_assure.contracts import CharSpan, Document, FindingKind, Severity
from usdm4_assure.layout import CellSpan, TableGrid, pymupdf_adapter
from usdm4_assure.soa import stitch
from usdm4_assure.soa.continuation import has_continued_cue, norm

ROOT = Path(__file__).resolve().parents[1]
LABELS = sorted((ROOT / "data" / "labels" / "soa").glob("*.json"))


# --- real labelled SoAs ------------------------------------------------------- #
def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _name_ratio(label: str, raw: str) -> float:
    """Labels hold cleaned names; raw cells keep footnote letters, split
    subscripts ('SpO h 2') and full wording. Compare against the raw prefix."""
    a = _alnum(label)
    return SequenceMatcher(None, a, _alnum(raw)[:len(a) + 3]).ratio()


@pytest.mark.parametrize("label_path", LABELS, ids=[p.stem for p in LABELS])
def test_labelled_soa_is_reproduced(label_path):
    lab = json.loads(label_path.read_text(encoding="utf-8"))
    pdf = ROOT / lab["source_pdf"]
    if not pdf.exists():
        pytest.skip(f"usdm_data corpus not present ({pdf.name})")
    pages = lab["pages"]
    # Two pages either side, so over- and under-merging at the boundaries both show up.
    window = range(max(1, pages[0] - 2), pages[-1] + 3)
    res = stitch(pymupdf_adapter.extract_tables(pdf, window))

    matches = [g for g in res.grids if g.pages == pages]
    assert matches, f"no stitched grid spans exactly {pages}: {[g.pages for g in res.grids]}"
    g = matches[0]
    assert res.findings_for(g) == []
    assert g.n_header_rows == lab["n_header_rows"]
    assert len(g.data_columns()) == lab["n_cols"]

    rows, data = g.activity_rows(), g.data_columns()
    assert len(rows) == len(lab["activities"])
    agree = total = 0
    for name, row in zip(lab["activities"], rows, strict=True):
        assert row[0].page == lab["page_of_activity"][name], name
        assert _name_ratio(name, row[0].text) >= 0.75, (name, row[0].text)
        got = {i for i, j in enumerate(data) if row[j].text}
        for i in range(len(data)):
            total += 1
            agree += (i in got) == (i in lab["marks"][name])
    # Exact marks are task 2.6's gate; here, agreement shows the columns line up.
    assert agree / total >= 0.95


# --- synthetic multi-page table, end to end ------------------------------------ #
N_ACTIVITIES = 80


def _build_long_soa(path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    header = [["", "Screening", "Treatment", "Treatment", "Follow-up"],
              ["Visit", "V1", "V2", "V3", "V4"],
              ["Day", "-14", "1", "29", "57"]]
    body = [[f"Activity {i:02d}"] + ["X" if (i + v) % 3 == 0 else "" for v in range(4)]
            for i in range(N_ACTIVITIES)]
    table = Table(header + body, repeatRows=3, colWidths=[160, 80, 80, 80, 80])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    SimpleDocTemplate(str(path), pagesize=letter).build([table])
    return path


def test_synthetic_multipage_table_stitches_into_one_grid(tmp_path):
    pdf = _build_long_soa(tmp_path / "long_soa.pdf")
    tables = pymupdf_adapter.extract_tables(pdf)
    assert len({t.page for t in tables}) >= 3  # the fixture really spans pages

    res = stitch(tables)
    assert len(res.grids) == 1 and res.findings == []
    g = res.grids[0]
    assert g.pages == sorted({t.page for t in tables})
    assert g.n_header_rows == 3
    labels = [row[0].text for row in g.activity_rows()]
    expected = [f"Activity {i:02d}" for i in range(N_ACTIVITIES)
                if any((i + v) % 3 == 0 for v in range(4))]
    assert labels == expected
    assert all(c.page in g.pages and c.bbox for row in g.body for c in row if c.text)


# --- in-memory rules ------------------------------------------------------------ #
HEADER = [["", "V1", "V2"], ["Activity", "Day 1", "Day 8"]]
EDGES = (50.0, 200.0, 260.0, 320.0)


def _grid(page, rows, edges=EDGES, top=100.0, geometry=True):
    h = 20.0
    cells = [[CellSpan(t, (edges[j], top + r * h, edges[j + 1], top + (r + 1) * h)
                       if geometry else None)
              for j, t in enumerate(texts)] for r, texts in enumerate(rows)]
    bbox = (edges[0], top, edges[-1], top + len(rows) * h) if geometry else None
    return TableGrid(page=page, method="pymupdf", bbox=bbox, cells=cells)


def _body(*labels):
    return [[lab, "X", ""] for lab in labels]


def _doc_with_text(page: int, text: str, y: float) -> Document:
    chars = [CharSpan(ch, page, (50.0 + 5 * i, y, 55.0 + 5 * i, y + 10)) for i, ch in enumerate(text)]
    return Document(source=Path("x.pdf"), blocks=[], full_text=text, chars={page: chars})


def _only_error(res):
    errors = [f for f in res.findings if f.severity is Severity.ERROR]
    assert len(errors) == 1 and errors[0].kind is FindingKind.STITCH
    return errors[0]


def test_repeated_header_merges_and_is_stored_once():
    res = stitch([_grid(1, HEADER + _body("A", "B")), _grid(2, HEADER + _body("C"))])
    assert len(res.grids) == 1 and res.findings == []
    g = res.grids[0]
    assert g.pages == [1, 2] and g.n_header_rows == 2
    assert [r[0].text for r in g.body] == ["A", "B", "C"]
    assert [r[0].page for r in g.body] == [1, 1, 2]


def test_headerless_continuation_without_cue_is_ambiguous_not_merged():
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, _body("B"))])
    assert len(res.grids) == 2
    assert res.unresolved == [(1, 2)]
    assert "no repeated header" in _only_error(res).message


def test_continued_cue_above_table_merges_headerless_continuation():
    doc = _doc_with_text(2, "Table 1 Schedule of Activities (continued)", y=60.0)
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, _body("B"))], doc=doc)
    assert len(res.grids) == 1 and res.findings == []
    assert res.grids[0].pages == [1, 2]


def test_continued_cue_without_geometry_is_ambiguous():
    tables = [_grid(1, HEADER + _body("A"), geometry=False),
              _grid(2, [["Table 1 (continued)", "", ""], *_body("B")], geometry=False)]
    res = stitch(tables)
    assert len(res.grids) == 2
    assert "no cell geometry" in _only_error(res).message


def test_repeated_header_without_geometry_still_merges():
    tables = [_grid(1, HEADER + _body("A"), geometry=False),
              _grid(2, HEADER + _body("B"), geometry=False)]
    assert len(stitch(tables).grids) == 1


def test_column_drift_under_a_repeated_header_is_ambiguous():
    drifted = [["", "V1", "V2", "V3"], ["Activity", "Day 1", "Day 8", "Day 15"],
               ["C", "X", "", ""]]
    res = stitch([_grid(1, HEADER + _body("A")),
                  _grid(2, drifted, edges=(50.0, 200.0, 260.0, 320.0, 380.0))])
    assert len(res.grids) == 2
    err = _only_error(res)
    assert "column drift" in err.message
    assert (err.expected, err.found) == ("3 columns", "4 columns")


def test_header_text_in_shifted_columns_is_ambiguous():
    shifted = [["V1", "", "V2"], ["Activity", "Day 1", "Day 8"], ["C", "X", ""]]
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, shifted)])
    assert "different columns" in _only_error(res).message


def test_new_table_caption_above_repeated_header_is_ambiguous():
    doc = _doc_with_text(2, "Table 2 Schedule of Activities, Part B", y=60.0)
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, HEADER + _body("B"))], doc=doc)
    assert len(res.grids) == 2
    assert "caption" in _only_error(res).message


def test_misaligned_column_widths_are_ambiguous():
    res = stitch([_grid(1, HEADER + _body("A")),
                  _grid(2, HEADER + _body("B"), edges=(50.0, 150.0, 260.0, 320.0))])
    assert "widths differ" in _only_error(res).message


def test_horizontal_page_shift_with_same_widths_still_merges():
    shifted = tuple(x + 18.0 for x in EDGES)
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, HEADER + _body("B"), edges=shifted)])
    assert len(res.grids) == 1 and res.findings == []


def test_partial_header_repeat_on_a_later_page_is_ambiguous():
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, HEADER + _body("B")),
                  _grid(3, HEADER[:1] + _body("C"))])
    assert [g.pages for g in res.grids] == [[1, 2], [3]]
    assert "only 1 of the table's 2 header rows" in _only_error(res).message


def test_non_adjacent_pages_and_mid_page_tables_are_separate_silently():
    gap = stitch([_grid(1, HEADER + _body("A")), _grid(3, HEADER + _body("B"))])
    assert len(gap.grids) == 2 and gap.findings == []
    # Page 2's repeated-header table is second on its page, so it isn't the
    # continuation of page 1's table.
    other = _grid(2, [["Dose", "mg"], ["Arm A", "10"]], edges=(50.0, 200.0, 260.0), top=100.0)
    mid = stitch([_grid(1, HEADER + _body("A")), other,
                  _grid(2, HEADER + _body("B"), top=400.0)])
    assert len(mid.grids) == 3 and mid.findings == []


def test_content_free_sliver_column_is_dropped_before_comparison():
    sliver = [[*row[:2], None, row[2]] for row in HEADER + _body("B")]
    rows = [[t or "" for t in row] for row in sliver]
    res = stitch([_grid(1, HEADER + _body("A")),
                  _grid(2, rows, edges=(50.0, 200.0, 258.0, 260.0, 320.0))])
    assert len(res.grids) == 1 and res.findings == []
    assert res.grids[0].segments[1].dropped_columns == (2,)


def test_unlabelled_first_row_on_continuation_page_warns():
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, HEADER + [["", "X", ""]] + _body("B"))])
    assert len(res.grids) == 1
    warn = [f for f in res.findings if f.severity is Severity.WARNING]
    assert len(warn) == 1 and "page 2" in warn[0].message


def test_issue_is_linked_to_both_grids_at_its_page_break_only():
    unrelated = _grid(5, HEADER + _body("Z"))
    res = stitch([_grid(1, HEADER + _body("A")), _grid(2, _body("B")), unrelated])
    before, after, other = res.grids
    assert res.findings_for(before) == res.findings_for(after) == res.findings
    assert res.findings_for(other) == []
    assert res.issues[0].pages == (1, 2)


def test_discontinued_is_not_a_continuation_cue():
    assert not has_continued_cue("Study treatment discontinued")
    assert has_continued_cue("Table 3 (cont.)") and has_continued_cue("Schedule, cont'd")
    assert norm("Visit (continued)") == "visit"


def test_annotation_column_is_not_a_data_column():
    header = [["", "V1", "Notes"], ["Activity", "Day 1", ""]]
    g = stitch([_grid(1, header + [["A", "X", "see 8.2"]]),
                _grid(2, header + [["B", "", "fasting"]])]).grids[0]
    assert g.annotation_columns() == [2] and g.data_columns() == [1]
    assert [r[0].text for r in g.activity_rows()] == ["A"]  # B has only a note
