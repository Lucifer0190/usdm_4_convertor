"""SoA cross-validation — the Assurance layer applied to table cells.

Takes the grids from each independent method and produces one AssuredGrid where
every cell carries a provenance tag and a decision. Agreement across methods is
what earns auto-accept; a cell seen by only one method is routed to review.
"""
from __future__ import annotations

from usdm4_assure.extract.soa.grid import AssuredCell, AssuredGrid, SoAGrid


def _reference(grids: list[SoAGrid]) -> SoAGrid:
    """The most complete grid defines the canonical labels/dimensions."""
    return max(grids, key=lambda g: (len(g.activities), len(g.visits), len(g.cells)))


def cross_validate(grids: list[SoAGrid]) -> AssuredGrid:
    grids = [g for g in grids if g.visits and g.activities]
    if not grids:
        return AssuredGrid([], [], [], [], [], set(), [])

    ref = _reference(grids)
    methods = [g.method for g in grids]
    n_methods = len(grids)
    na, nv = len(ref.activities), len(ref.visits)

    cells: list[AssuredCell] = []
    for a in range(na):
        for v in range(nv):
            seers = [g for g in grids if g.marked(a, v)]
            k = len(seers)
            present = k >= 1
            if k == n_methods and n_methods >= 2:
                prov, conf, dec = "both", 0.97, "auto_accept"
            elif k >= 1 and n_methods >= 2 and k < n_methods:
                prov = f"{seers[0].method}-only"
                conf, dec = 0.55, "review"
            elif k == n_methods == 1:
                prov, conf, dec = f"{seers[0].method}-only", 0.6, "review"
            else:
                prov, conf, dec = "none", 0.9, "auto_accept"  # confident absence
            if present or prov == "none":
                cells.append(AssuredCell(a, v, present, prov, conf, dec))

    # footnote-gated activities: union across methods (a conservative catch)
    foot = set()
    for g in grids:
        foot |= g.footnote_activities

    return AssuredGrid(
        epochs=ref.epochs, visits=ref.visits, timings=ref.timings,
        activities=ref.activities, cells=cells, footnote_activities=foot,
        methods=methods,
    )
