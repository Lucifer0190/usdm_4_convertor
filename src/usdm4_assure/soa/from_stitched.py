"""Bridge a stitched grid (task 2.3) into the legacy ``SoAGrid`` shape.

``extract/soa/crossval.py`` and ``assemble/soa.py`` (Phase 1 spine, already
tested end to end through the ``TimelineAssembler``) work over ``SoAGrid``'s
3-row header convention: epoch row, visit row, timing row. Converting here
means table *detection* gets multi-page-aware (task 2.3's stitcher) without
rewriting that already-working cross-validation and assembly path.

Real protocols don't all have a 3-row header — the five labelled SoAs
(``data/labels/soa/``) show 1 to 4 — so :func:`stitched_to_soa_grid` returns
``None`` for anything else rather than guessing which rows are epoch/visit/
timing. Generalizing ``SoAGrid``/``TimelineAssembler`` beyond that shape is
future work, not silently-wrong output today.
"""
from __future__ import annotations

import dataclasses
import re

from usdm4_assure.extract.soa.grid import SoAGrid
from usdm4_assure.soa.stitch import StitchedGrid

# The 3-row (epoch/visit/timing) header assumption `extract/soa/methods.py`'s
# legacy `_parse_rows` has always made for every SoA table.
DEFAULT_HEADER_ROWS = 3

_MARK_RE = re.compile(r"[xX✓✔●•]")
_FOOTNOTE_RE = re.compile(r"\s[a-z]$")


def is_mark(text: str | None) -> bool:
    return bool(text and _MARK_RE.search(text.strip()))


def _ffill(values: list[str]) -> list[str]:
    out, last = [], ""
    for v in values:
        last = v or last
        out.append(last)
    return out


def normalize_header(grid: StitchedGrid, default_header_rows: int = DEFAULT_HEADER_ROWS
                     ) -> StitchedGrid:
    """Ensure ``grid.header``/``grid.body`` are split, falling back when unconfirmed.

    ``grid.n_header_rows`` is only set when the stitcher *confirmed* it via a
    repeated header on a continuation page (task 2.3) — a table that never
    continues has no such confirmation, and every row sits in ``grid.body``
    with an empty ``grid.header``. This re-draws that split at
    ``default_header_rows``, the same fixed assumption the legacy single-page
    ``_parse_rows`` has always made. A grid whose header *was* confirmed is
    returned unchanged. Every reader of ``grid.header``/``grid.data_columns()``/
    ``grid.activity_rows()`` (this module, ``vision_cells.read_grid``,
    ``rederive``) must call this first, or an unconfirmed grid's header rows
    leak into the body as if they were activities.
    """
    if grid.n_header_rows is not None:
        return grid
    all_rows = grid.header + grid.body
    return dataclasses.replace(grid, header=all_rows[:default_header_rows],
                               body=all_rows[default_header_rows:],
                               n_header_rows=default_header_rows)


def stitched_to_soa_grid(grid: StitchedGrid) -> SoAGrid | None:
    """Convert a 3-header-row ``StitchedGrid`` to the legacy ``SoAGrid`` shape.

    Returns:
        A populated ``SoAGrid``, or ``None`` if the effective header (after
        :func:`normalize_header`) is not exactly 3 rows.
    """
    grid = normalize_header(grid)
    if grid.n_header_rows != 3 or len(grid.header) < 3:
        return None
    epoch_row, visit_row, timing_row = grid.header
    data_cols = grid.data_columns()

    g = SoAGrid(method=grid.method)
    g.epochs = _ffill([epoch_row[j].text for j in data_cols])
    g.visits = [visit_row[j].text for j in data_cols]
    g.timings = [timing_row[j].text for j in data_cols]

    for row in grid.activity_rows():
        label = row[0].text.strip()
        foot = bool(_FOOTNOTE_RE.search(label))
        if foot:
            label = _FOOTNOTE_RE.sub("", label).strip()
        ai = len(g.activities)
        g.activities.append(label)
        if foot:
            g.footnote_activities.add(label)
        for vi, j in enumerate(data_cols):
            if is_mark(row[j].text):
                g.cells.add((ai, vi))
    return g
