"""MinerU2.5 table adapter — the one small-model specialist this project keeps
(DEVPLAN.md §M: 88.2 TEDS vs Gemini-2.5-Pro 85.7 on table structure).

Optional dependency (``pip install usdm4-assure[layout]``). Returns ``[]`` when
MinerU2.5 is not installed, mirroring `docling_adapter`. Not yet wired into
Phase 2's grid structural-agreement signal — that's task 2.4.
"""
from __future__ import annotations

from pathlib import Path

from usdm4_assure.layout.base import CellSpan, TableGrid


def available() -> bool:
    try:
        import mineru  # noqa: F401
    except ImportError:
        return False
    return True


def extract_tables(pdf_path: str | Path) -> list[TableGrid]:
    """Return every table MinerU2.5 detects, or ``[]`` if MinerU is not installed."""
    if not available():
        return []

    from mineru.backend.pipeline.pipeline_analyze import doc_analyze

    result = doc_analyze(str(pdf_path))
    grids: list[TableGrid] = []
    for table in result.tables:
        rows = table.cell_grid
        cells = [[CellSpan(text=(cell.text or "").strip()) for cell in row] for row in rows]
        grids.append(TableGrid(page=table.page_no, method="mineru", cells=cells))
    return grids
