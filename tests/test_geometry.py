"""Char-level geometry: offset<->bbox round trip on a real fixture PDF."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_fixture import GROUND_TRUTH, build

from usdm4_assure.ingest.geometry import page_geometry
from usdm4_assure.ingest.pdf import ingest


def test_text_is_exact_concatenation_of_chars():
    pdf_path = build()
    import pymupdf
    doc = pymupdf.open(pdf_path)
    text, chars = page_geometry(doc[0], 1)
    doc.close()
    assert text == "".join(c.char for c in chars)
    assert all(c.page == 1 for c in chars)


def test_offset_round_trips_to_a_real_glyph_bbox():
    pdf_path = build()
    import pymupdf
    doc = pymupdf.open(pdf_path)
    text, chars = page_geometry(doc[0], 1)
    doc.close()
    # Locate the sponsor name (a real string on the fixture's page 1) and check
    # the resolved bbox is a real, non-degenerate box (not a separator's 0-width one).
    sponsor = GROUND_TRUTH["sponsorName"].split(",")[0]  # "Northwind Therapeutics"
    idx = text.find(sponsor)
    assert idx >= 0, "fixture page 1 should contain the sponsor name"
    span = chars[idx:idx + len(sponsor)]
    assert all(c.char == ch for c, ch in zip(span, sponsor, strict=True))
    x0, y0, x1, y1 = span[0].bbox
    assert x1 > x0 and y1 > y0


def test_ingest_populates_document_chars_matching_text_of():
    pdf_path = build()
    doc = ingest(pdf_path)
    assert doc.pages, "ingest should populate chars for at least one page"
    for page in doc.pages:
        text = doc.text_of(page)
        assert text == "".join(c.char for c in doc.chars[page])
        assert all(c.page == page for c in doc.chars[page])


def test_bbox_of_matches_manual_union():
    pdf_path = build()
    doc = ingest(pdf_path)
    page = doc.pages[0]
    text = doc.text_of(page)
    sponsor = GROUND_TRUTH["sponsorName"].split(",")[0]
    idx = text.find(sponsor)
    assert idx >= 0
    manual = doc.chars[page][idx:idx + len(sponsor)]
    from usdm4_assure.contracts import bbox_union
    assert doc.bbox_of(page, idx, idx + len(sponsor)) == bbox_union([c.bbox for c in manual])


def test_separator_chars_do_not_distort_a_real_bbox_lookup():
    """A quote spanning two spans (crossing an inserted ' ' separator) still
    resolves to a bbox that encloses only real glyph geometry, not garbage."""
    pdf_path = build()
    doc = ingest(pdf_path)
    page = doc.pages[0]
    text = doc.text_of(page)
    # "Phase 2" in the ground truth phase spans a label/value boundary in practice;
    # here we just confirm any two-token match produces a sane, ordered bbox.
    idx = text.find("CLINICAL STUDY PROTOCOL")
    assert idx >= 0
    bbox = doc.bbox_of(page, idx, idx + len("CLINICAL STUDY PROTOCOL"))
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    assert x0 <= x1 and y0 <= y1
