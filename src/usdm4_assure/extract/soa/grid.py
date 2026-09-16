"""The SoA intermediate representation — a normalized grid.

Each extraction method (pdfplumber, pymupdf, vision) returns one of these; the
cross-validation step reconciles multiple grids cell-by-cell.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SoAGrid:
    method: str
    epochs: list[str] = field(default_factory=list)     # per visit column
    visits: list[str] = field(default_factory=list)     # column labels (V1..)
    timings: list[str] = field(default_factory=list)    # per visit column
    activities: list[str] = field(default_factory=list)  # row labels
    cells: set[tuple[int, int]] = field(default_factory=set)  # (activity_i, visit_i) marked
    footnote_activities: set[str] = field(default_factory=set)

    def marked(self, a: int, v: int) -> bool:
        return (a, v) in self.cells

    def stats(self) -> dict:
        return {"method": self.method, "visits": len(self.visits),
                "activities": len(self.activities), "marks": len(self.cells)}


# A cell after cross-validation: which methods saw it, and the verdict.
@dataclass
class AssuredCell:
    activity_i: int
    visit_i: int
    present: bool
    provenance: str          # both | pdfplumber-only | pymupdf-only | vision-only | none
    confidence: float
    decision: str            # auto_accept | review


@dataclass
class AssuredGrid:
    epochs: list[str]
    visits: list[str]
    timings: list[str]
    activities: list[str]
    cells: list[AssuredCell]
    footnote_activities: set[str]
    methods: list[str]

    def present_cells(self) -> list[AssuredCell]:
        return [c for c in self.cells if c.present]

    def triage(self) -> dict:
        out = {"auto_accept": 0, "review": 0}
        for c in self.present_cells():
            out[c.decision] += 1
        return out
