"""L1 VLM cell-content pass (task 2.5) — replaces the ``extract_vision`` no-op.

DEVPLAN.md §M: the table-structure specialist (MinerU2.5, task 2.1) beats
frontier vision-LLMs on *structure*; frontier VLMs are stronger on *cell
text*. This module owns the content half: crop each cell out of the rendered
page (PyMuPDF ``clip``, never a whole-page image an LLM would have to search),
ask the ``vision`` role what it says, and escalate to a different-family
``vision_alt`` model only when that reading disagrees with what the grid
already parsed — most cells never need a second call.

Vision is duck-typed, not part of the ``LLM`` protocol (``llm/base.py``):
most ensemble members are text-only, so a member simply not offering
``complete_vision`` means "no vision reading here", not an error.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path

from usdm4_assure.contracts import BBox
from usdm4_assure.llm.base import LLM
from usdm4_assure.soa.stitch import StitchedGrid

_PROMPT = (
    "This image is one cell from a clinical trial Schedule of Activities table. "
    "Reply with exactly what the cell contains: 'X' for a mark (X, checkmark, "
    "filled dot), the visible text verbatim, or 'EMPTY' if the cell is blank. "
    "Reply with nothing else."
)

_WS_RE = re.compile(r"\s+")


def _norm(text: str | None) -> str:
    return _WS_RE.sub(" ", text or "").strip().lower()


def crop_cell(pdf_path: str | Path, page: int, bbox: BBox, zoom: float = 3.0) -> bytes:
    """Render one cell's bounding box as a PNG, upscaled for a small glyph or mark."""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        pix = doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=bbox)
        return pix.tobytes("png")
    finally:
        doc.close()


def _read(llm: LLM | None, image_png: bytes) -> str | None:
    """One vision call. ``None`` when the member has no vision capability,
    is unavailable, or the call fails — a bad vision member must not crash the run."""
    call = getattr(llm, "complete_vision", None)
    if llm is None or call is None or not getattr(llm, "available", False):
        return None
    try:
        return call(base64.b64encode(image_png).decode("ascii"), _PROMPT, max_tokens=20).strip()
    except Exception:  # noqa: BLE001
        return None


@dataclass(frozen=True)
class CellReading:
    """One cell's vision reading(s) against what the grid already claimed."""
    row: int
    col: int
    page: int
    bbox: BBox
    grid_text: str
    vision_text: str | None            # None: no vision reading available for this cell
    agrees_with_grid: bool | None      # None: no vision_text to compare
    vision_alt_text: str | None = None  # set only when vision disagreed with the grid


def read_cells(pdf_path: str | Path, cells: list[tuple[int, int, int, BBox, str]],
               vision: LLM, vision_alt: LLM | None = None) -> list[CellReading]:
    """Read a list of cells with the vision role, escalating on disagreement.

    Args:
        pdf_path: The source PDF; crops are rendered fresh (never a cached
            page image), so every reading keeps exact bbox provenance.
        cells: ``(row, col, page, bbox, grid_text)`` per cell to read —
            typically the disagreeing cells from :mod:`soa.grid_agreement`
            (task 2.4), or every data cell when no structural signal exists.
        vision: The frontier vision-role LLM.
        vision_alt: A different-family cross-check model, called only for a
            cell where ``vision``'s reading disagrees with ``grid_text``.
    """
    out = []
    for row, col, page, bbox, grid_text in cells:
        png = crop_cell(pdf_path, page, bbox)
        vtext = _read(vision, png)
        agree = None if vtext is None else _norm(vtext) == _norm(grid_text)
        vatext = _read(vision_alt, png) if vtext is not None and not agree else None
        out.append(CellReading(row, col, page, bbox, grid_text, vtext, agree, vatext))
    return out


def read_grid(pdf_path: str | Path, grid: StitchedGrid, vision: LLM,
              vision_alt: LLM | None = None, only: frozenset[tuple[int, int]] | None = None,
              *, body_offset: int = 0) -> list[CellReading]:
    """Read a :class:`StitchedGrid`'s activity-row data cells with the vision role.

    Args:
        grid: A stitched table (task 2.3); rows/cols index ``grid.body``.
        only: Cell keys to restrict to (e.g. task 2.4's disagreeing cells).
            ``None`` reads every activity-row data cell.
        body_offset: Row index of ``grid.activity_rows()``'s first row within
            ``grid.body``, needed to key readings the same way callers of
            :mod:`grid_agreement` do. Left ``0`` when the caller doesn't need
            that alignment.
    """
    from usdm4_assure.soa.from_stitched import normalize_header

    grid = normalize_header(grid)
    data_cols = grid.data_columns()
    cells = []
    for r, row in enumerate(grid.activity_rows(), start=body_offset):
        for c in data_cols:
            cell = row[c]
            if cell.bbox is None:
                continue
            if only is not None and (r, c) not in only:
                continue
            cells.append((r, c, cell.page, cell.bbox, cell.text))
    return read_cells(pdf_path, cells, vision, vision_alt)
