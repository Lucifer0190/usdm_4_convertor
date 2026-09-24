"""★ Multi-page Schedule-of-Activities stitcher (DESIGN.md L2) — the risk centre.

No available engine merges tables across pages correctly: Docling doesn't
merge (issue #2976) and MinerU drops content on continuation pages (#4311).
:func:`stitch` takes every table one engine found (a list of
:class:`~usdm4_assure.layout.base.TableGrid`) and joins each continuation onto
the table it continues. :mod:`usdm4_assure.soa.continuation` decides each page
break. Any break it can't decide becomes an ERROR
:class:`~usdm4_assure.contracts.Finding` and is left unmerged, so a human
resolves it; the stitcher never guesses in either direction. Every stitched
cell keeps the page and bbox it came from.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from usdm4_assure.contracts import BBox, Document, Finding, FindingKind, Severity
from usdm4_assure.layout.base import TableGrid
from usdm4_assure.soa.continuation import (
    CONTEXT_BAND,
    Signals,
    Verdict,
    classify,
    column_edges,
    drop_empty_columns,
    edges_aligned,
    has_continued_cue,
    new_caption_above,
    norm,
    repeated_header_rows,
    repeated_header_text,
    text_band,
)

_ANNOTATION_RE = re.compile(r"^(?:[a-z]\s+)?(?:notes?|comments?|remarks?)$")


@dataclass(frozen=True)
class StitchedCell:
    text: str
    page: int
    bbox: BBox | None


@dataclass(frozen=True)
class Segment:
    """One source table that became part of a stitched grid."""
    page: int
    bbox: BBox | None
    header_rows_skipped: int         # repeated header rows not copied again
    dropped_columns: tuple[int, ...]  # content-free source columns removed


@dataclass
class StitchedGrid:
    """One logical table, possibly spanning pages.

    ``header`` holds the header rows once. They are known (``n_header_rows``
    set) only when a continuation page repeated them; for a table seen on a
    single page, or joined only by a "(continued)" cue, the split between
    header and body is left to the caller (``n_header_rows is None`` and every
    row is in ``body``).
    """
    method: str
    segments: list[Segment]
    header: list[list[StitchedCell]]
    body: list[list[StitchedCell]]
    n_header_rows: int | None

    @property
    def pages(self) -> list[int]:
        return [s.page for s in self.segments]

    @property
    def n_cols(self) -> int:
        rows = self.header or self.body
        return len(rows[0]) if rows else 0

    def annotation_columns(self) -> list[int]:
        """Free-text Notes/Comments columns, identified by their header."""
        return [j for j in range(1, self.n_cols)
                if any(_ANNOTATION_RE.match(norm(row[j].text)) for row in self.header)]

    def data_columns(self) -> list[int]:
        """Visit/timepoint columns: everything except the label column and annotations."""
        notes = set(self.annotation_columns())
        return [j for j in range(1, self.n_cols) if j not in notes]

    def activity_rows(self) -> list[list[StitchedCell]]:
        """Body rows with a label and at least one filled visit cell. This leaves
        out section dividers ('Laboratory Tests'), blank rows and footnote rows."""
        data = self.data_columns()
        return [row for row in self.body
                if row[0].text and any(row[j].text for j in data)]


@dataclass(frozen=True)
class StitchIssue:
    """A finding about one page break, tied to the grid(s) it concerns."""
    finding: Finding
    pages: tuple[int, int]   # (page before the break, page after)
    grids: tuple[int, ...]   # indices into StitchResult.grids


@dataclass
class StitchResult:
    """Every stitched table from one engine, plus the page breaks it couldn't decide.

    The stitcher sees every table in the document (abbreviation lists,
    amendment histories, dose-modification tables), not just the SoA. Choosing
    which grid *is* the SoA happens later, so callers should read
    :meth:`findings_for` for the grid they use rather than every finding.
    """
    grids: list[StitchedGrid]
    issues: list[StitchIssue] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        return [i.finding for i in self.issues]

    @property
    def unresolved(self) -> list[tuple[int, int]]:
        """Page breaks left unmerged because the evidence conflicted."""
        return [i.pages for i in self.issues if i.finding.severity is Severity.ERROR]

    def findings_for(self, grid: StitchedGrid) -> list[Finding]:
        idx = next(i for i, g in enumerate(self.grids) if g is grid)
        return [i.finding for i in self.issues if idx in i.grids]


@dataclass
class _Chain:
    head: TableGrid
    last: TableGrid
    last_index: int
    parts: list[tuple[TableGrid, tuple[int, ...], int]]  # (grid, dropped columns, rows skipped)
    header_rows: int | None = None

    def build(self) -> StitchedGrid:
        rows = [[StitchedCell(c.text, g.page, c.bbox) for c in row]
                for g, _, skip in self.parts for row in g.cells[skip:]]
        k = self.header_rows or 0
        segments = [Segment(g.page, g.bbox, skip, dropped) for g, dropped, skip in self.parts]
        return StitchedGrid(self.head.method, segments, rows[:k], rows[k:], self.header_rows)


def _context(doc: Document | None, grid: TableGrid, above: bool) -> str | None:
    if grid.bbox is None:
        return None
    if above:
        return text_band(doc, grid.page, grid.bbox[1] - CONTEXT_BAND, grid.bbox[1])
    return text_band(doc, grid.page, grid.bbox[3], grid.bbox[3] + CONTEXT_BAND)


def _measure(chain: _Chain, cand: TableGrid, boundary: bool, doc: Document | None) -> Signals:
    above = _context(doc, cand, above=True)
    edge_cells = [c.text for c in cand.cells[0]] if cand.cells else []
    edge_cells += [c.text for c in chain.last.cells[-1]] if chain.last.cells else []
    head_edges, cand_edges = column_edges(chain.head), column_edges(cand)
    return Signals(
        page_adjacent=cand.page == chain.last.page + 1,
        at_page_boundary=boundary,
        n_cols_head=chain.head.n_cols,
        n_cols_cand=cand.n_cols,
        header_rows_repeated=repeated_header_rows(chain.head, cand),
        header_text_repeated=repeated_header_text(chain.head, cand),
        continued_cue=any(has_continued_cue(t) for t in
                          [*edge_cells, above, _context(doc, chain.last, above=False)]),
        new_table_caption=new_caption_above(above),
        columns_aligned=(edges_aligned(head_edges, cand_edges)
                         if head_edges is not None and cand_edges is not None else None),
    )


def _boundaries(tables: list[TableGrid]) -> tuple[list[bool], list[bool]]:
    """(first table on its page, last table on its page) for each table in page order."""
    first = [i == 0 or tables[i - 1].page != t.page for i, t in enumerate(tables)]
    last = [i == len(tables) - 1 or tables[i + 1].page != t.page for i, t in enumerate(tables)]
    return first, last


def stitch(tables: list[TableGrid], doc: Document | None = None) -> StitchResult:
    """Join every table that continues across a page break into one grid.

    Args:
        tables: Every table from one engine, any order. Tables from different
            engines should be stitched separately; comparing engines is a
            separate signal (task 2.4).
        doc: Optional ingested document. Its character geometry supplies the
            page text just above and below each table, where "(continued)"
            cues and new "Table N" captions appear. Without it, only cues
            inside the table cells are seen.

    Returns:
        The stitched grids in reading order. Each page break that couldn't be
        decided is an ERROR issue tied to the grids on both sides of it.
    """
    ordered = sorted(tables, key=lambda t: (t.page, t.bbox[1] if t.bbox else 0.0))
    first_on_page, last_on_page = _boundaries(ordered)
    issues: list[StitchIssue] = []
    chains: list[_Chain] = []

    for i, raw in enumerate(ordered):
        if chains:
            chain, idx = chains[-1], len(chains) - 1
            # Compact only on a column-count mismatch: a headerless continuation page
            # can have a real, mark-free visit column that must not be dropped.
            grid, dropped = ((raw, ()) if raw.n_cols == chain.head.n_cols
                             else drop_empty_columns(raw))
            boundary = last_on_page[chain.last_index] and first_on_page[i]
            sig = _measure(chain, grid, boundary, doc)
            verdict, reason = classify(sig, chain.header_rows)
            if verdict is Verdict.CONTINUATION:
                skip = 0
                if sig.header_rows_repeated:
                    chain.header_rows = chain.header_rows or sig.header_rows_repeated
                    skip = chain.header_rows
                if _split_row(grid, skip):
                    issues.append(StitchIssue(Finding(
                        FindingKind.STITCH, Severity.WARNING, "soa",
                        f"First row continued onto page {grid.page} has no activity label; "
                        f"it may be the end of a row that started on page {chain.last.page}."),
                        (chain.last.page, grid.page), (idx,)))
                chain.parts.append((grid, dropped, skip))
                chain.last, chain.last_index = grid, i
                continue
            if verdict is Verdict.AMBIGUOUS:
                issues.append(StitchIssue(Finding(
                    FindingKind.STITCH, Severity.ERROR, "soa",
                    f"Table on page {grid.page} may continue the table on page "
                    f"{chain.last.page} ({reason}). Kept as separate tables; "
                    f"confirm whether they are one table.",
                    expected=f"{sig.n_cols_head} columns", found=f"{sig.n_cols_cand} columns"),
                    (chain.last.page, grid.page), (idx, idx + 1)))
        # A chain head carries its own header rows, so its empty columns are safe to drop.
        grid, dropped = drop_empty_columns(raw)
        chains.append(_Chain(head=grid, last=grid, last_index=i, parts=[(grid, dropped, 0)]))

    return StitchResult([c.build() for c in chains], issues)


def _split_row(grid: TableGrid, skip: int) -> bool:
    """A continuation page whose first body row has cells but no label is usually
    one row broken across the page. It gets flagged, not silently joined."""
    if len(grid.cells) <= skip:
        return False
    row = grid.cells[skip]
    return not row[0].text and any(c.text for c in row[1:])
