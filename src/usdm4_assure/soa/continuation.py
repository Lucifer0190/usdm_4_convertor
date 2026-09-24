"""Continuation evidence for the multi-page SoA stitcher (DESIGN.md L2).

Each function here measures one kind of evidence that a table at the top of
page N+1 continues a table at the bottom of page N. :func:`classify` combines
them into a :class:`Verdict`. The rule it encodes: merge only on positive,
mutually consistent evidence; when the evidence conflicts, return
``AMBIGUOUS`` so a person decides. Both failure modes are unacceptable in a
Schedule of Activities: a wrong merge splices two schedules together, and a
missed merge silently drops every row after the page break.
"""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from enum import Enum

from usdm4_assure.contracts import Document
from usdm4_assure.layout.base import CellSpan, TableGrid

# Column-edge jitter between pages of one table is <1pt on the labelled corpus.
EDGE_TOL = 3.0
# How far above/below a table (points) to look for "(continued)" or a caption.
CONTEXT_BAND = 72.0
# Header rows at least this similar (difflib ratio over cell texts) count as
# the same header when looking for column drift. One added column in a 3-column
# header scores 0.8.
HEADER_SIMILARITY = 0.75

# "continued", "cont'd", "contd", "cont." — the leading \b keeps
# "discontinued" (a common SoA column header) from matching.
_CONTINUED_RE = re.compile(r"\(?\s*\bcont(?:inued|['’]d|d\b|\.)\s*\)?", re.IGNORECASE)
_CAPTION_RE = re.compile(r"(?:^|\n)\s*table\s+\d+(?:[.-]\d+)*\b", re.IGNORECASE)


class Verdict(str, Enum):
    CONTINUATION = "continuation"
    SEPARATE = "separate"
    AMBIGUOUS = "ambiguous"


def norm(text: str | None) -> str:
    """Cell text for comparison: continuation cues removed, whitespace collapsed, lowercased."""
    return " ".join(_CONTINUED_RE.sub(" ", text or "").split()).lower()


def has_continued_cue(text: str | None) -> bool:
    return bool(text and _CONTINUED_RE.search(text))


def drop_empty_columns(grid: TableGrid) -> tuple[TableGrid, tuple[int, ...]]:
    """Remove columns with no text in any row, returning the grid and the removed indices.

    PyMuPDF adds content-free sliver columns wherever a merged cell's edge
    doesn't line up with the grid, and where they appear changes from page to
    page. Dropping them loses nothing *if the grid has its header rows*, since
    the header names every real column. A headerless continuation page can
    have a real visit column with no marks on it, which is why the stitcher
    only compacts a candidate whose raw column count doesn't match.
    """
    keep = [j for j in range(grid.n_cols) if any(row[j].text for row in grid.cells)]
    dropped = tuple(j for j in range(grid.n_cols) if j not in keep)
    if not dropped:
        return grid, ()
    return replace(grid, cells=[[row[j] for j in keep] for row in grid.cells]), dropped


def column_edges(grid: TableGrid) -> list[float] | None:
    """Left x of each column, then the table's right x. ``None`` without full geometry."""
    if grid.n_cols == 0:
        return None
    edges: list[float] = []
    for j in range(grid.n_cols):
        xs = [row[j].bbox[0] for row in grid.cells if row[j].bbox]
        if not xs:
            return None
        edges.append(min(xs))
    edges.append(max(c.bbox[2] for row in grid.cells for c in row if c.bbox))
    return edges


def edges_aligned(a: list[float], b: list[float], tol: float = EDGE_TOL) -> bool:
    """Same column widths, allowing the whole table to shift horizontally
    (odd/even page margins move a table without changing its layout)."""
    if len(a) != len(b):
        return False
    return all(abs((x - a[0]) - (y - b[0])) <= tol for x, y in zip(a, b, strict=True))


def _count_repeated(head: TableGrid, cand: TableGrid, key, same=operator.eq) -> int:
    """How many leading rows match. Matches that are all blank don't count
    as evidence, so if nothing non-blank matched the answer is 0."""
    k, informative = 0, False
    for ra, rb in zip(head.cells, cand.cells, strict=False):
        ka, kb = key(ra), key(rb)
        if not same(ka, kb):
            break
        k += 1
        informative = informative or any(ka)
    return k if informative else 0


def _similar(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    return bool(a and b) and SequenceMatcher(None, a, b, autojunk=False).ratio() >= HEADER_SIMILARITY


def _cell_key(row: list[CellSpan]) -> tuple[str, ...]:
    return tuple(norm(c.text) for c in row)


def _text_key(row: list[CellSpan]) -> tuple[str, ...]:
    return tuple(t for t in (norm(c.text) for c in row) if t)


def repeated_header_rows(head: TableGrid, cand: TableGrid) -> int:
    """Leading rows of ``cand`` that repeat ``head``'s leading rows cell for cell."""
    if head.n_cols != cand.n_cols:
        return 0
    return _count_repeated(head, cand, _cell_key)


def repeated_header_text(head: TableGrid, cand: TableGrid) -> int:
    """Leading rows whose non-empty cell texts nearly match, wherever they sit.
    This catches what :func:`repeated_header_rows` misses: a header that
    repeats after its columns have moved, gained a column or lost one."""
    return _count_repeated(head, cand, _text_key, _similar)


def text_band(doc: Document | None, page: int, y0: float, y1: float) -> str | None:
    """Text of ``page`` whose glyph centres lie between ``y0`` and ``y1``; ``None``
    when there is no character geometry to look at."""
    if doc is None or page not in doc.chars:
        return None
    return "".join(c.char for c in doc.chars[page]
                   if c.bbox and y0 <= (c.bbox[1] + c.bbox[3]) / 2 <= y1)


def new_caption_above(text: str | None) -> bool:
    """A 'Table N' caption that is not marked as a continuation, e.g.
    'Table 2 Schedule of Activities, Part B' but not 'Table 1 (continued)'."""
    return bool(text and _CAPTION_RE.search(text) and not has_continued_cue(text))


@dataclass(frozen=True)
class Signals:
    """Everything measured about one (previous table, candidate table) pair."""
    page_adjacent: bool
    at_page_boundary: bool      # previous is last on its page, candidate first on its page
    n_cols_head: int
    n_cols_cand: int
    header_rows_repeated: int   # cell for cell, same columns
    header_text_repeated: int   # same text, any columns
    continued_cue: bool
    new_table_caption: bool
    columns_aligned: bool | None  # None: an engine without cell geometry

    @property
    def same_n_cols(self) -> bool:
        return self.n_cols_head == self.n_cols_cand


def classify(s: Signals, expected_header_rows: int | None = None) -> tuple[Verdict, str]:
    """Decide one page break. Returns the verdict and a human-readable reason.

    Args:
        s: The measured signals.
        expected_header_rows: Header rows the chain has already established
            from an earlier repeat. A later page repeating *fewer* is a conflict.
    """
    if not (s.page_adjacent and s.at_page_boundary):
        return Verdict.SEPARATE, "not across a page boundary"

    evidence = s.header_rows_repeated or s.header_text_repeated or s.continued_cue
    if not evidence:
        if s.same_n_cols and s.columns_aligned:
            return Verdict.AMBIGUOUS, ("identical column layout across the page break but "
                                       "no repeated header and no continuation cue")
        return Verdict.SEPARATE, "no continuation evidence"

    if s.new_table_caption:
        return Verdict.AMBIGUOUS, "a new 'Table N' caption sits above an apparent continuation"
    if not s.same_n_cols:
        return Verdict.AMBIGUOUS, (f"column drift: continuation evidence, but "
                                   f"{s.n_cols_head} columns become {s.n_cols_cand}")
    if s.columns_aligned is False:
        return Verdict.AMBIGUOUS, "same column count but the column widths differ"
    if s.header_rows_repeated:
        if expected_header_rows and s.header_rows_repeated < expected_header_rows:
            return Verdict.AMBIGUOUS, (f"only {s.header_rows_repeated} of the table's "
                                       f"{expected_header_rows} header rows repeat")
        return Verdict.CONTINUATION, "repeated header"
    if s.header_text_repeated:
        return Verdict.AMBIGUOUS, "header text repeats but sits in different columns"
    if s.columns_aligned:
        return Verdict.CONTINUATION, "continuation cue with identical column layout"
    return Verdict.AMBIGUOUS, "continuation cue, but no cell geometry to confirm the layout"
