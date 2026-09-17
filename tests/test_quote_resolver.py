"""L5 quote resolver: exact, normalized, multi-line, ligature, not-found,
page-boundary cases."""
from __future__ import annotations

from pathlib import Path

from usdm4_assure.contracts import CharSpan, Document, VerifyPass
from usdm4_assure.ground.quote import resolve_quote


def _doc(pages: dict[int, str]) -> Document:
    """Build a Document whose page geometry is exactly the given strings,
    each char at a distinct 1-pt-wide box so bbox math is easy to check."""
    chars: dict[int, list[CharSpan]] = {}
    for page, text in pages.items():
        chars[page] = [CharSpan(ch, page, (float(i), 0.0, float(i + 1), 10.0))
                       for i, ch in enumerate(text)]
    return Document(source=Path("x.pdf"), blocks=[],
                    full_text="\n".join(pages.values()), chars=chars)


def test_exact_match():
    doc = _doc({1: "The Protocol Number is NWT-ABC123-201 for this study."})
    q = resolve_quote(doc, "NWT-ABC123-201")
    assert q.ok and q.verify_pass is VerifyPass.EXACT
    assert q.page == 1
    text = doc.text_of(1)
    assert text[q.char_start:q.char_end] == "NWT-ABC123-201"
    assert q.bbox == (23.0, 0.0, 37.0, 10.0)


def test_normalized_whitespace_collapse():
    doc = _doc({1: "Sponsor:   Northwind\n\nTherapeutics, Inc."})
    q = resolve_quote(doc, "Sponsor: Northwind Therapeutics, Inc.")
    assert q.ok and q.verify_pass is VerifyPass.NORMALIZED
    assert doc.text_of(1)[q.char_start:q.char_end] == "Sponsor:   Northwind\n\nTherapeutics, Inc."


def test_normalized_multi_line_quote_spans_a_line_break():
    doc = _doc({1: "This is a randomized,\ndouble-blind study of ABC-123."})
    q = resolve_quote(doc, "randomized, double-blind study")
    assert q.ok and q.verify_pass is VerifyPass.NORMALIZED
    assert q.page == 1
    assert q.bbox is not None


def test_normalized_ligature_fi():
    doc = _doc({1: "The deﬁnitive endpoint is progression-free survival."})
    q = resolve_quote(doc, "definitive endpoint")
    assert q.ok and q.verify_pass is VerifyPass.NORMALIZED


def test_normalized_soft_hyphen_is_dropped():
    doc = _doc({1: "This is a random­ized trial."})
    q = resolve_quote(doc, "randomized trial")
    assert q.ok and q.verify_pass is VerifyPass.NORMALIZED


def test_normalized_smart_quotes_fold_to_ascii():
    doc = _doc({1: "The sponsor’s protocol “title” is final."})
    q = resolve_quote(doc, "sponsor's protocol \"title\" is final")
    assert q.ok and q.verify_pass is VerifyPass.NORMALIZED


def test_not_found_is_a_hard_reject():
    doc = _doc({1: "This document says nothing about the claimed value."})
    q = resolve_quote(doc, "a completely fabricated sentence")
    assert not q.ok
    assert q.verify_pass is VerifyPass.FAILED
    assert q.page is None and q.bbox is None and q.char_start is None


def test_empty_or_blank_query_is_a_hard_reject():
    doc = _doc({1: "Some real text on the page."})
    assert not resolve_quote(doc, "").ok
    assert not resolve_quote(doc, "   ").ok


def test_page_boundary_does_not_merge_two_pages():
    # "study of ABC" ends page 1; "-123 in adults" starts page 2 — the quote
    # must not resolve by concatenating across the page boundary.
    doc = _doc({1: "This is a study of ABC", 2: "-123 in adults with the condition."})
    q = resolve_quote(doc, "ABC-123")
    assert not q.ok


def test_page_argument_restricts_search():
    doc = _doc({1: "Phase 2 study of drug ABC-123.", 2: "Phase 2 study of drug ABC-123."})
    q = resolve_quote(doc, "ABC-123", page=2)
    assert q.ok and q.page == 2


def test_exact_pass_preferred_over_normalized_across_pages():
    # Page 1 only matches after normalization (extra spaces); page 2 has an
    # exact match. Exact-anywhere must win over normalized-anywhere.
    doc = _doc({1: "ABC   123", 2: "ABC123"})
    q = resolve_quote(doc, "ABC123")
    assert q.verify_pass is VerifyPass.EXACT
    assert q.page == 2


def test_missing_page_geometry_is_skipped_not_matched():
    doc = Document(source=Path("x.pdf"), blocks=[], full_text="ABC123", chars={})
    q = resolve_quote(doc, "ABC123")
    assert not q.ok
