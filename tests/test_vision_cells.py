"""VLM cell-content pass (task 2.5): crop provenance, agreement, and
vision_alt escalation only on disagreement — all against a stub vision LLM."""
from __future__ import annotations

from pathlib import Path

import pytest

from usdm4_assure.soa.stitch import Segment, StitchedCell, StitchedGrid
from usdm4_assure.soa.vision_cells import crop_cell, read_cells, read_grid

EDGES = (50.0, 200.0, 260.0)


def _build_pdf(path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    data = [["", "V1"], ["Vitals", "X"]]
    table = Table(data, colWidths=[150, 60])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    SimpleDocTemplate(str(path), pagesize=letter).build([table])
    return path


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    return _build_pdf(tmp_path_factory.mktemp("vc") / "cells.pdf")


class _StubVision:
    """A vision-capable LLM member: reads back a fixed text per call count."""

    def __init__(self, replies: list[str] | None = None, available: bool = True):
        self.available = available
        self.name = "vision-stub"
        self._replies = replies or []
        self.calls: list[str] = []  # base64 payloads passed, for call-count assertions

    def complete_vision(self, image_b64, prompt, *, system=None, max_tokens=20, mime="image/png"):
        self.calls.append(image_b64)
        i = len(self.calls) - 1
        return self._replies[i] if i < len(self._replies) else self._replies[-1]


class _StubTextOnly:
    """A member with no vision capability at all — the common case."""
    available = True
    name = "text-only-stub"

    def complete(self, prompt, **kw):
        raise AssertionError("text-only member should never be called for vision")


def test_crop_cell_renders_a_real_png(pdf):
    png = crop_cell(pdf, page=1, bbox=(50.0, 50.0, 260.0, 100.0))
    assert png.startswith(b"\x89PNG")
    assert len(png) > 100


def test_read_cells_marks_agreement_and_records_provenance(pdf):
    vision = _StubVision(["X"])
    cells = [(0, 0, 1, (50.0, 50.0, 260.0, 80.0), "X")]
    out = read_cells(pdf, cells, vision)
    assert len(out) == 1
    r = out[0]
    assert (r.row, r.col, r.page, r.bbox) == (0, 0, 1, (50.0, 50.0, 260.0, 80.0))
    assert r.vision_text == "X" and r.agrees_with_grid is True
    assert r.vision_alt_text is None


def test_disagreement_escalates_to_vision_alt(pdf):
    vision = _StubVision(["EMPTY"])
    alt = _StubVision(["EMPTY"])
    cells = [(0, 0, 1, (50.0, 50.0, 260.0, 80.0), "X")]  # grid says X, vision says EMPTY
    out = read_cells(pdf, cells, vision, vision_alt=alt)
    assert out[0].agrees_with_grid is False
    assert out[0].vision_alt_text == "EMPTY"
    assert len(alt.calls) == 1


def test_agreement_never_calls_vision_alt(pdf):
    vision = _StubVision(["X"])
    alt = _StubVision(["X"])
    cells = [(0, 0, 1, (50.0, 50.0, 260.0, 80.0), "X")]
    read_cells(pdf, cells, vision, vision_alt=alt)
    assert alt.calls == []


def test_member_without_vision_capability_yields_none_not_a_crash(pdf):
    cells = [(0, 0, 1, (50.0, 50.0, 260.0, 80.0), "X")]
    out = read_cells(pdf, cells, _StubTextOnly())
    assert out[0].vision_text is None and out[0].agrees_with_grid is None
    assert out[0].vision_alt_text is None


def test_unavailable_vision_member_yields_none(pdf):
    cells = [(0, 0, 1, (50.0, 50.0, 260.0, 80.0), "X")]
    out = read_cells(pdf, cells, _StubVision(["X"], available=False))
    assert out[0].vision_text is None


def test_whitespace_and_case_agree(pdf):
    vision = _StubVision(["  vital  signs "])
    cells = [(0, 0, 1, (50.0, 50.0, 260.0, 80.0), "Vital Signs")]
    assert read_cells(pdf, cells, vision)[0].agrees_with_grid is True


# --- read_grid: StitchedGrid integration ------------------------------------- #
def _cell(text, page=1, col=0, row=0):
    x0 = EDGES[col]
    return StitchedCell(text, page, (x0, 100.0 + row * 20, x0 + 60, 120.0 + row * 20))


def _grid():
    header = [[_cell(""), _cell("V1", col=1)]]
    body = [[_cell("Vitals", row=1), _cell("X", col=1, row=1)],
            [_cell("", row=2), _cell("", col=1, row=2)]]  # fully-blank row, not an activity
    segments = [Segment(page=1, bbox=None, header_rows_skipped=0, dropped_columns=())]
    return StitchedGrid("pymupdf", segments, header, body, n_header_rows=1)


def test_read_grid_reads_every_activity_row_data_cell_by_default(pdf):
    vision = _StubVision(["X"])
    out = read_grid(pdf, _grid(), vision)
    assert len(out) == 1  # only the one real activity row has data cells
    assert (out[0].row, out[0].col) == (0, 1)


def test_read_grid_only_filter_restricts_to_given_cells(pdf):
    vision = _StubVision(["X"])
    out = read_grid(pdf, _grid(), vision, only=frozenset())
    assert out == []
