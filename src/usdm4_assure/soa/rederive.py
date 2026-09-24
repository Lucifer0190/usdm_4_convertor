"""Mechanical mark-matrix re-derivation (task 2.6) — the soa2usdm pattern.

``find_tables()``'s cell text is itself a claim, built from PyMuPDF's own
line/span reconstruction, which can occasionally merge, drop or misattribute
a glyph at a cell boundary. This module answers "is this cell marked" a
second, independent way: scan the source document's raw character geometry
(``ingest.geometry`` / ``Document.chars``) for a mark glyph whose bbox falls
inside the cell, without going through the table parser's cell text at all.

Disagreements are never applied automatically — see :mod:`soa.corrections`
for the sidecar that records them without touching the raw extraction.
"""
from __future__ import annotations

from dataclasses import dataclass

from usdm4_assure.contracts import BBox, Document, Finding, FindingKind, Severity
from usdm4_assure.soa.from_stitched import is_mark, normalize_header
from usdm4_assure.soa.stitch import StitchedGrid

_MARK_GLYPHS = frozenset("xX✓✔●•")


def glyphs_in_bbox(doc: Document, page: int, bbox: BBox) -> str:
    """Every character on ``page`` whose glyph centre falls inside ``bbox``, in reading order."""
    x0, y0, x1, y1 = bbox
    out = []
    for c in doc.chars.get(page, []):
        cx0, cy0, cx1, cy1 = c.bbox
        cx, cy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            out.append(c.char)
    return "".join(out)


def rederive_mark(doc: Document, page: int, bbox: BBox) -> bool:
    """Is this cell marked, purely from glyph geometry — no cell-text claim used."""
    return any(ch in _MARK_GLYPHS for ch in glyphs_in_bbox(doc, page, bbox))


@dataclass(frozen=True)
class MarkComparison:
    """One activity-row data cell: what extraction claimed vs. what glyph geometry found."""
    row: int
    col: int
    page: int
    activity: str
    claimed: bool
    rederived: bool

    @property
    def agree(self) -> bool:
        return self.claimed == self.rederived


def rederive_grid(doc: Document, grid: StitchedGrid) -> list[MarkComparison]:
    """Compare every activity-row data cell's claimed mark against a mechanical
    glyph-geometry re-derivation. ``grid`` is normalized first (see
    ``from_stitched.normalize_header``); a cell with no bbox (e.g. a synthetic
    grid in a test) can't be re-derived and is reported as agreeing.
    """
    grid = normalize_header(grid)
    data_cols = grid.data_columns()
    out = []
    for r, row in enumerate(grid.activity_rows()):
        activity = row[0].text
        for c in data_cols:
            cell = row[c]
            claimed = is_mark(cell.text)
            rederived = rederive_mark(doc, cell.page, cell.bbox) if cell.bbox is not None else claimed
            out.append(MarkComparison(r, c, cell.page, activity, claimed, rederived))
    return out


def disagreements(comparisons: list[MarkComparison]) -> list[MarkComparison]:
    return [c for c in comparisons if not c.agree]


def as_findings(comparisons: list[MarkComparison], domain: str = "soa") -> list[Finding]:
    """One WARNING Finding per disagreement. This only flags a cell for review —
    the value extraction claimed is left untouched; see :mod:`soa.corrections`."""
    return [
        Finding(
            FindingKind.STITCH, Severity.WARNING, domain,
            f"'{c.activity}' col {c.col} (page {c.page}): extraction says "
            f"{'marked' if c.claimed else 'blank'}, mechanical glyph re-derivation says "
            f"{'marked' if c.rederived else 'blank'}.",
            field=c.activity, expected=str(c.claimed), found=str(c.rederived),
        )
        for c in disagreements(comparisons)
    ]
