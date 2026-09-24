"""PyMuPDF table adapter — wraps ``page.find_tables()`` into the common `TableGrid` IR.

Always available (PyMuPDF is a core dependency, not an optional layout extra).
Cells carry their bounding box; a cell covered by a merged neighbour has
``bbox=None`` (PyMuPDF puts a merged cell's text and box in its leftmost column).
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from usdm4_assure.layout.base import CellSpan, TableGrid


def available() -> bool:
    return True


def extract_tables(pdf_path: str | Path, pages: Iterable[int] | None = None) -> list[TableGrid]:
    """Return every table PyMuPDF detects, in page then top-to-bottom order.

    Args:
        pdf_path: The source PDF.
        pages: Optional 1-indexed page numbers to restrict detection to.
    """
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    wanted = sorted(set(pages)) if pages is not None else range(1, doc.page_count + 1)
    grids: list[TableGrid] = []
    try:
        for pno in wanted:
            if not 1 <= pno <= doc.page_count:
                continue
            for t in doc[pno - 1].find_tables().tables:
                cells = [
                    [CellSpan(text=str(text).strip() if text else "",
                              bbox=tuple(box) if box else None)
                     for text, box in zip(texts, row.cells, strict=True)]
                    for texts, row in zip(t.extract(), t.rows, strict=True)
                ]
                grids.append(TableGrid(page=pno, method="pymupdf",
                                       bbox=tuple(t.bbox), cells=cells))
    finally:
        doc.close()
    return grids
