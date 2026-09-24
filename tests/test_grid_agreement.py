"""Cross-engine structural agreement (task 2.4): agree/disagree/no-signal cases."""
from __future__ import annotations

from usdm4_assure.layout.base import CellSpan, TableGrid
from usdm4_assure.soa.grid_agreement import (
    cells_needing_vision,
    compare_by_page,
    compare_grids,
)


def _grid(page, method, texts):
    return TableGrid(page=page, method=method, cells=[[CellSpan(t) for t in row] for row in texts])


def test_identical_grids_fully_agree():
    a = _grid(1, "pymupdf", [["", "V1"], ["Vitals", "X"]])
    b = _grid(1, "docling", [["", "V1"], ["Vitals", "X"]])
    g = compare_grids(a, b)
    assert g.has_signal and g.dims_match
    assert g.n_cells_compared == 4 and g.n_agree == 4
    assert g.agreement_ratio == 1.0
    assert g.disagreements == ()


def test_one_cell_mismatch_is_reported():
    a = _grid(1, "pymupdf", [["", "V1"], ["Vitals", "X"]])
    b = _grid(1, "docling", [["", "V1"], ["Vitals", ""]])
    g = compare_grids(a, b)
    assert g.n_agree == 3 and len(g.disagreements) == 1
    d = g.disagreements[0]
    assert (d.row, d.col) == (1, 1) and d.text_a == "X" and d.text_b == ""
    assert g.disagreeing_cells() == frozenset({(1, 1)})


def test_whitespace_and_case_differences_are_not_disagreement():
    a = _grid(1, "pymupdf", [["Vital  Signs"]])
    b = _grid(1, "docling", [["vital signs"]])
    assert compare_grids(a, b).n_agree == 1


def test_dimension_mismatch_compares_the_overlap_and_flags_dims():
    a = _grid(1, "pymupdf", [["", "V1", "V2"], ["Vitals", "X", "X"]])
    b = _grid(1, "docling", [["", "V1"], ["Vitals", "X"]])
    g = compare_grids(a, b)
    assert not g.dims_match
    assert g.n_cells_compared == 4  # min(2,2) rows x min(3,2) cols
    assert g.n_agree == 4


def test_compare_by_page_matches_same_page_tables():
    prim = [_grid(1, "pymupdf", [["A"]]), _grid(2, "pymupdf", [["B"]])]
    other = [_grid(2, "docling", [["B"]]), _grid(1, "docling", [["A"]])]
    results = compare_by_page(prim, other)
    assert [g.page for g in results] == [1, 2]
    assert all(g.has_signal and g.n_agree == 1 for g in results)


def test_compare_by_page_reports_no_signal_when_other_engine_absent():
    prim = [_grid(1, "pymupdf", [["A"]])]
    results = compare_by_page(prim, [])  # docling/mineru unavailable -> []
    assert results == [type(results[0])(page=1, has_signal=False, method_a="pymupdf")]
    assert results[0].agreement_ratio == 1.0  # no evidence of disagreement


def test_compare_by_page_positional_match_for_multiple_tables_on_one_page():
    prim = [_grid(1, "pymupdf", [["A"]]), _grid(1, "pymupdf", [["B"]])]
    other = [_grid(1, "docling", [["A"]]), _grid(1, "docling", [["Z"]])]
    results = compare_by_page(prim, other)
    assert results[0].n_agree == 1 and results[1].n_agree == 0


def test_cells_needing_vision_excludes_no_signal_and_full_agreement():
    disagree = compare_grids(_grid(1, "pymupdf", [["", "V1"], ["Vitals", "X"]]),
                             _grid(1, "docling", [["", "V1"], ["Vitals", ""]]))
    agree = compare_grids(_grid(2, "pymupdf", [["A"]]), _grid(2, "docling", [["A"]]))
    no_signal = type(agree)(page=3, has_signal=False)
    routing = cells_needing_vision([disagree, agree, no_signal])
    assert len(routing) == 1
    assert routing[0].page == 1 and routing[0].cells == frozenset({(1, 1)})


def test_empty_grid_has_zero_comparable_cells_and_full_ratio():
    g = compare_grids(TableGrid(1, "pymupdf"), TableGrid(1, "docling"))
    assert g.n_cells_compared == 0 and g.agreement_ratio == 1.0
