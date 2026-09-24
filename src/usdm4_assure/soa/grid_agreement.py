"""L1 cross-engine structural agreement signal (task 2.4).

Comparing two independent table-structure engines over the same table region
is the cheapest quality signal available before spending a model call: where
they agree cell-for-cell, the structure is almost certainly right; where they
disagree, that cell is exactly the case the VLM pass (2.5) should spend its
budget reading.

This needs two engines to have actually produced a grid for the same table.
In this repository that is the common-but-not-guaranteed case: PyMuPDF always
runs; Docling and MinerU2.5 are optional (`layout/docling_adapter.py`,
`layout/mineru_adapter.py`) and return ``[]`` when their packages aren't
installed. :func:`compare_grids` reports ``has_signal=False`` rather than
inventing agreement or disagreement from a comparison that never happened.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from usdm4_assure.layout.base import TableGrid

CellKey = tuple[int, int]  # (row, col)

_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip().lower()


@dataclass(frozen=True)
class CellAgreement:
    """One compared cell."""
    row: int
    col: int
    text_a: str
    text_b: str
    agree: bool


@dataclass(frozen=True)
class GridAgreement:
    """Structural agreement between two engines' view of one table.

    Comparison is over the region both grids cover
    (``min(rows_a, rows_b) x min(cols_a, cols_b)``); a dimension mismatch is
    itself recorded (``dims_match``), since two engines finding a different
    table shape is a strong disagreement signal on its own, separate from any
    individual cell's text.
    """
    page: int
    has_signal: bool             # False: fewer than two engines produced a grid here
    method_a: str | None = None
    method_b: str | None = None
    dims_match: bool | None = None
    n_cells_compared: int = 0
    n_agree: int = 0
    disagreements: tuple[CellAgreement, ...] = ()

    @property
    def agreement_ratio(self) -> float:
        """1.0 when nothing was compared — no evidence of disagreement is not evidence of it."""
        return self.n_agree / self.n_cells_compared if self.n_cells_compared else 1.0

    def disagreeing_cells(self) -> frozenset[CellKey]:
        return frozenset((d.row, d.col) for d in self.disagreements)


def compare_grids(a: TableGrid, b: TableGrid) -> GridAgreement:
    """Compare two engines' grids for what should be the same table.

    Args:
        a: One engine's ``TableGrid`` (e.g. PyMuPDF).
        b: Another engine's ``TableGrid`` for the same table region (e.g. Docling).
    """
    rows, cols = min(a.n_rows, b.n_rows), min(a.n_cols, b.n_cols)
    disagreements = []
    n_agree = 0
    for r in range(rows):
        for c in range(cols):
            ta, tb = a.cells[r][c].text, b.cells[r][c].text
            agree = _norm(ta) == _norm(tb)
            n_agree += agree
            if not agree:
                disagreements.append(CellAgreement(r, c, ta, tb, agree))
    return GridAgreement(
        page=a.page, has_signal=True, method_a=a.method, method_b=b.method,
        dims_match=(a.n_rows, a.n_cols) == (b.n_rows, b.n_cols),
        n_cells_compared=rows * cols, n_agree=n_agree,
        disagreements=tuple(disagreements),
    )


def compare_by_page(primary: list[TableGrid], other: list[TableGrid]) -> list[GridAgreement]:
    """Pair each of ``primary``'s tables with a same-page table in ``other``.

    Tables are matched by page number, in order of appearance on that page —
    real SoAs have at most one table per page, which this assumes; a page
    with more than one table region pairs them positionally.

    Returns one :class:`GridAgreement` per table in ``primary``, in order.
    A ``primary`` table with no same-page match in ``other`` gets
    ``has_signal=False`` (e.g. ``other`` is an unavailable optional engine).
    """
    by_page: dict[int, list[TableGrid]] = {}
    for t in other:
        by_page.setdefault(t.page, []).append(t)
    seen: dict[int, int] = {}

    results = []
    for t in primary:
        i = seen.get(t.page, 0)
        seen[t.page] = i + 1
        candidates = by_page.get(t.page, [])
        if i < len(candidates):
            results.append(compare_grids(t, candidates[i]))
        else:
            results.append(GridAgreement(page=t.page, has_signal=False, method_a=t.method))
    return results


@dataclass(frozen=True)
class VisionRouting:
    """Which cells structural disagreement says are worth a vision read."""
    page: int
    cells: frozenset[CellKey] = field(default_factory=frozenset)


def cells_needing_vision(agreements: list[GridAgreement]) -> list[VisionRouting]:
    """The disagreeing cells from every agreement that actually had a signal.

    A ``GridAgreement`` with ``has_signal=False`` contributes nothing here —
    "we didn't compare" must never look like "we compared and disagreed".
    """
    return [VisionRouting(g.page, g.disagreeing_cells())
            for g in agreements if g.has_signal and g.disagreements]
