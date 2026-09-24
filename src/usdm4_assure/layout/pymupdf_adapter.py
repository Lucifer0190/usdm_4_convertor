"""PyMuPDF table adapter — wraps ``page.find_tables()`` into the common `TableGrid` IR.

Always available (PyMuPDF is a core dependency, not an optional layout extra).
"""
from __future__ import annotations

from pathlib import Path

from usdm4_assure.layout.base import CellSpan, TableGrid


def available() -> bool:
    return True


def extract_tables(pdf_path: str | Path) -> list[TableGrid]:
    """Return every table PyMuPDF detects, across every page."""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    grids: list[TableGrid] = []
    try:
        for page in doc:
            finder = page.find_tables()
            for t in finder.tables:
                rows = t.extract()
                cells = [[CellSpan(text=str(c).strip() if c else "") for c in row]
                         for row in rows]
                grids.append(TableGrid(page=page.number + 1, method="pymupdf",
                                       bbox=tuple(t.bbox), cells=cells))
    finally:
        doc.close()
    return grids
