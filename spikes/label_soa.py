"""Helper for hand-labelling multi-page Schedule-of-Activities ground truth.

Scans a protocol PDF for pages whose PyMuPDF `find_tables()` detects a table
and whose text mentions a Schedule-of-Activities heading, so a human labeller
can quickly locate candidate page ranges instead of paging through a 100+ page
protocol by hand. Prints a candidate list; it does not label anything itself —
labels are hand-authored JSON under `data/labels/soa/<nct>.json` (task 2.2).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HEADING_RE = ["schedule of activities", "schedule of assessments",
               "schedule of procedures", "study schedule", "time and events"]


def find_candidate_pages(pdf_path: str | Path) -> list[int]:
    """1-indexed page numbers that look like SoA table pages."""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    candidates: list[int] = []
    try:
        for page in doc:
            text = page.get_text().lower()
            has_heading = any(h in text for h in _HEADING_RE)
            has_table = bool(page.find_tables().tables)
            if has_heading or has_table:
                candidates.append(page.number + 1)
    finally:
        doc.close()
    return candidates


def _table_dims(pdf_path: str | Path, page_no: int) -> list[tuple[int, int]]:
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        page = doc[page_no - 1]
        return [(len(t.extract()), len(t.extract()[0]) if t.extract() else 0)
                for t in page.find_tables().tables]
    finally:
        doc.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python label_soa.py <pdf_path> [page_no ...]")
        sys.exit(1)
    path = sys.argv[1]
    if len(sys.argv) > 2:
        for p in sys.argv[2:]:
            print(f"page {p}: table dims {_table_dims(path, int(p))}")
    else:
        pages = find_candidate_pages(path)
        print(f"{path}: {len(pages)} candidate page(s): {pages}")
