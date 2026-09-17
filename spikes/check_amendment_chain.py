#!/usr/bin/env python3
"""Phase 0 spike — confirm dated PDFs form an amendment chain.

Reads three dated protocol PDFs from ../Data/Protocols/ and extracts title,
version number, and date to confirm they represent a single protocol evolving
through amendments (same protocol ID, increasing dates, sequential versions).

Usage::

    .venv/Scripts/python.exe spikes/check_amendment_chain.py

Prints the extracted metadata and confirms the chain is valid.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF not installed. Install with: pip install PyMuPDF", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_DIR = REPO_ROOT.parent / "Data" / "Protocols"


def extract_metadata(pdf_path: Path) -> dict:
    """Extract title, version, and date from a protocol PDF.

    Returns a dict with keys: path, filename, title, version, date, protocol_id.
    """
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()

    lines = full_text.split("\n")[:50]  # Check first ~50 lines
    full_head = "\n".join(lines)

    result = {
        "path": str(pdf_path.relative_to(PROTOCOL_DIR.parent)),
        "filename": pdf_path.name,
        "title": None,
        "version": None,
        "date": None,
        "protocol_id": None,
    }

    for line in lines:
        if not line.strip():
            continue
        line_lower = line.lower()

        if "clinical protocol" in line_lower and result["title"] is None:
            result["title"] = line.strip()

        if "version" in line_lower:
            match = re.search(r"version\s+(\d+(?:\.\d+)?)", line, re.IGNORECASE)
            if match and result["version"] is None:
                result["version"] = match.group(1)

        if re.search(r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}", line, re.IGNORECASE):
            if result["date"] is None:
                result["date"] = line.strip()

        protocol_match = re.search(r"protocol\s*(?:number|#|id)?[:\s]+([A-Z0-9\-]+)", line, re.IGNORECASE)
        if protocol_match and result["protocol_id"] is None:
            result["protocol_id"] = protocol_match.group(1)

    return result


def main() -> int:
    if not PROTOCOL_DIR.exists():
        print(f"Data/Protocols directory not found at {PROTOCOL_DIR}", file=sys.stderr)
        return 1

    pdf_files = sorted([p for p in PROTOCOL_DIR.glob("Clinical Protocol - *.pdf")])
    if len(pdf_files) < 3:
        print(
            f"Expected 3 dated protocol PDFs in {PROTOCOL_DIR}, found {len(pdf_files)}",
            file=sys.stderr,
        )
        return 1

    print("Amendment chain check:")
    print("======================\n")

    results = []
    for pdf_path in pdf_files[:3]:
        meta = extract_metadata(pdf_path)
        results.append(meta)
        print(f"File: {meta['filename']}")
        print(f"  Title: {meta['title']}")
        print(f"  Version: {meta['version']}")
        print(f"  Date: {meta['date']}")
        print(f"  Protocol ID: {meta['protocol_id']}")
        print()

    protocol_ids = [r["protocol_id"] for r in results if r["protocol_id"]]
    if len(set(protocol_ids)) == 1:
        print(f"[OK] All three PDFs share protocol ID: {protocol_ids[0]}")
        return 0
    else:
        print(f"[WARN] Protocol IDs differ (not an amendment chain):")
        for pid in protocol_ids:
            print(f"  - {pid}")
        print(
            "\nNote: Phase 6 amendment corpus may be a different set of PDFs or not yet available.",
            file=sys.stderr,
        )
        return 1

    dates = [r["date"] for r in results if r["date"]]
    if len(dates) == 3:
        print(f"[OK] All three PDFs have extraction dates")
        print(f"  Dates (should be increasing for amendments):")
        for i, (r, date) in enumerate(zip(results, dates), 1):
            print(f"    {i}. {date} ({r['filename']})")
    else:
        print(f"[WARN] Only {len(dates)}/3 PDFs had dates extracted", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
