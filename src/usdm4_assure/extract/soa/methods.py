"""Independent SoA table extractors — the ensemble members for the SoA grid.

  pdfplumber : ruling-line based table detection
  pymupdf    : PyMuPDF's own find_tables() — a different implementation
  vision     : multimodal LLM over the rendered page image (drop-in with a key)

Two independent deterministic implementations give a real agreement signal for
the cross-validation step without needing an LLM.
"""
from __future__ import annotations

import re
from pathlib import Path

from usdm4_assure.extract.soa.grid import SoAGrid
from usdm4_assure.llm.base import LLM

_MARK_RE = re.compile(r"[xX✓✔●•]")


def _is_mark(cell: str | None) -> bool:
    return bool(cell and _MARK_RE.search(cell.strip()))


def _parse_rows(rows: list[list[str | None]], method: str) -> SoAGrid:
    """Rows: [epochRow, visitRow, timingRow, *activityRows]; col 0 = row label."""
    g = SoAGrid(method=method)
    rows = [r for r in rows if r and any(c and str(c).strip() for c in r)]
    if len(rows) < 4:
        return g
    epoch_row, visit_row, timing_row, *body = rows

    def clean(cells: list) -> list[str]:
        return [(str(c).strip() if c else "") for c in cells[1:]]

    g.epochs = _ffill(clean(epoch_row))     # forward-fill spanned epoch cells
    g.visits = clean(visit_row)
    g.timings = clean(timing_row)
    ncol = len(g.visits)

    for ai, row in enumerate(body):
        label = (str(row[0]).strip() if row and row[0] else "")
        if not label:
            continue
        foot = bool(re.search(r"\s[a-z]$", label))   # trailing footnote marker
        label = re.sub(r"\s+[a-z]$", "", label).strip()
        g.activities.append(label)
        if foot:
            g.footnote_activities.add(label)
        for vi in range(min(ncol, len(row) - 1)):
            if _is_mark(row[vi + 1]):
                g.cells.add((len(g.activities) - 1, vi))
    return g


def _ffill(vals: list[str]) -> list[str]:
    out, last = [], ""
    for v in vals:
        last = v or last
        out.append(last)
    return out


def extract_pdfplumber(pdf_path: str | Path) -> SoAGrid:
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for t in tables:
                g = _parse_rows(t, "pdfplumber")
                if g.visits and g.activities:
                    return g
    return SoAGrid(method="pdfplumber")


def extract_pymupdf(pdf_path: str | Path) -> SoAGrid:
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    try:
        for page in doc:
            finder = page.find_tables()
            for t in finder.tables:
                g = _parse_rows(t.extract(), "pymupdf")
                if g.visits and g.activities:
                    return g
    finally:
        doc.close()
    return SoAGrid(method="pymupdf")


def extract_vision(page_images: list[Path], llm: LLM) -> SoAGrid | None:
    """Drop-in third member: read the grid geometry from the page image.

    Only runs when a multimodal LLM key is present. Returns None otherwise so the
    deterministic members carry the run (same pattern as the metadata extractor).
    """
    if not getattr(llm, "available", False) or not page_images:
        return None
    # Wired when a key is available: send image + strict-JSON grid prompt.
    # Kept as an explicit no-op here so the deterministic path is the tested one.
    return None
