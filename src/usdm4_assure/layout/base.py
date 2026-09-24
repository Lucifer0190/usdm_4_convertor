"""Common table-grid IR shared by every layout/table-structure engine (L1-L2).

PyMuPDF, Docling, and MinerU2.5 each detect tables differently, but downstream
code (multi-page stitching in Phase 2, cross-validation) doesn't need to care
which engine produced a table — it only needs a page-located grid of cells.
Every adapter in this package returns a list of `TableGrid`, nothing engine-
specific leaks past this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class CellSpan:
    """One table cell: its text and (if the engine reports one) bounding box."""
    text: str
    bbox: BBox | None = None


@dataclass
class TableGrid:
    """One detected table's structure, as a 2D grid of cells.

    Attributes:
        page: 1-indexed page the table starts on.
        method: which engine produced this grid (``"pymupdf"`` | ``"docling"`` |
            ``"mineru"``).
        bbox: bounding box of the whole table on that page, if the engine reports one.
        cells: ``cells[row][col] -> CellSpan``. Row 0 is typically the header row.
    """
    page: int
    method: str
    bbox: BBox | None = None
    cells: list[list[CellSpan]] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.cells)

    @property
    def n_cols(self) -> int:
        return len(self.cells[0]) if self.cells else 0

    def text_grid(self) -> list[list[str]]:
        """Cell text only — the shape `extract/soa/methods._parse_rows` expects."""
        return [[c.text for c in row] for row in self.cells]
