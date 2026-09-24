"""Docling table adapter — layout + reading order via IBM's Docling library.

Optional dependency (``pip install usdm4-assure[layout]``). Mirrors the
LLM-unavailable pattern used elsewhere in this codebase: a missing optional
layout engine returns ``[]`` rather than crashing the run, so the deterministic
PyMuPDF path always carries the pipeline. Not yet wired into Phase 2's grid
structural-agreement signal — that's task 2.4.
"""
from __future__ import annotations

from pathlib import Path

from usdm4_assure.layout.base import CellSpan, TableGrid


def available() -> bool:
    try:
        import docling  # noqa: F401
    except ImportError:
        return False
    return True


def extract_tables(pdf_path: str | Path) -> list[TableGrid]:
    """Return every table Docling detects, or ``[]`` if Docling is not installed."""
    if not available():
        return []

    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    grids: list[TableGrid] = []
    for table in result.document.tables:
        page = table.prov[0].page_no if table.prov else 1
        rows = table.data.grid
        cells = [[CellSpan(text=(cell.text or "").strip()) for cell in row] for row in rows]
        grids.append(TableGrid(page=page, method="docling", cells=cells))
    return grids
