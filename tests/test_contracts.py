"""Type-level tests for the Phase 1 contracts (no PDF, no LLM)."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from usdm4_assure.contracts import (
    AssuredField,
    CharSpan,
    Decision,
    Document,
    FieldCandidate,
    Finding,
    FindingKind,
    GroundedCandidate,
    Method,
    Quote,
    Severity,
    VerifyPass,
    bbox_union,
    to_grounded,
)
from usdm4_assure.contracts_audit import AuditEvent, AuditRecord, replace_fields


def _doc_with_chars(text: str, page: int = 1) -> Document:
    chars = [CharSpan(ch, page, (float(i), 0.0, float(i + 1), 10.0))
             for i, ch in enumerate(text)]
    return Document(source=Path("x.pdf"), blocks=[], full_text=text, chars={page: chars})


# --- Document geometry ------------------------------------------------------ #
def test_text_of_offsets_index_chars():
    doc = _doc_with_chars("Study ABC-123")
    text = doc.text_of(1)
    assert text == "Study ABC-123"
    start = text.index("ABC")
    assert doc.chars[1][start].char == "A"
    assert doc.bbox_of(1, start, start + 3) == (6.0, 0.0, 9.0, 10.0)


def test_text_of_missing_page_is_empty_not_block_text():
    doc = Document(source=Path("x.pdf"), blocks=[], full_text="block text")
    assert doc.text_of(1) == ""
    assert doc.bbox_of(1, 0, 5) is None
    assert doc.pages == []


def test_bbox_union():
    assert bbox_union([]) is None
    assert bbox_union([(1, 2, 3, 4), (0, 5, 2, 6)]) == (0, 2, 3, 6)


# --- Quote / GroundedCandidate --------------------------------------------- #
def test_quote_failed_is_not_ok_and_has_no_location():
    q = Quote.failed("not in doc")
    assert not q.ok
    assert q.page is None and q.bbox is None
    assert q.as_row()["verify_pass"] == "failed"


def test_quote_is_immutable():
    q = Quote("t", VerifyPass.EXACT, page=1, char_start=0, char_end=1, bbox=(0, 0, 1, 1))
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("vp", [VerifyPass.EXACT, VerifyPass.NORMALIZED])
def test_grounded_candidate_grounded_when_quote_resolved(vp):
    q = Quote("Phase 2", vp, page=3, char_start=10, char_end=17, bbox=(1, 2, 3, 4))
    c = GroundedCandidate("studyPhase", "Phase 2", Method.LLM_FRONTIER, q,
                          model_id="anthropic/claude-sonnet-4.5", prompt_hash="abc")
    assert c.grounded and c.page == 3 and c.bbox == (1, 2, 3, 4)


def test_grounded_candidate_not_grounded_on_failed_or_missing_quote():
    assert not GroundedCandidate("f", "v", Method.LLM_FRONTIER, Quote.failed("v")).grounded
    human = GroundedCandidate("f", "v", Method.HUMAN)
    assert not human.grounded and human.page is None


def test_method_enum_values_are_stable():
    assert {m.value for m in Method} == {
        "det_text", "det_table", "llm_small", "llm_frontier", "vision", "human"}


def test_to_grounded_bridges_legacy_candidate_conservatively():
    legacy = FieldCandidate("studyTitle", "A Study", "titlepage", "A Study of X", 1)
    g = to_grounded(legacy, Method.DET_TEXT, domain="metadata")
    assert g.field == "studyTitle" and g.method is Method.DET_TEXT
    assert g.quote is not None and g.quote.text == "A Study of X"
    assert not g.grounded  # nothing is grounded until the resolver says so


# --- AssuredField review row ----------------------------------------------- #
def test_review_row_exposes_page_and_bbox_and_mixed_sources():
    q = Quote("A Study", VerifyPass.EXACT, page=1, char_start=0, char_end=7, bbox=(0, 0, 7, 10))
    cands = [
        FieldCandidate("studyTitle", "A Study", "titlepage", "A Study", 1),
        GroundedCandidate("studyTitle", "A Study", Method.LLM_FRONTIER, q, "openai/gpt-5.1"),
    ]
    a = AssuredField("studyTitle", "A Study", cands, True, 2, "supported", 0.9,
                     Decision.AUTO_ACCEPT, quote=q, domain="metadata")
    row = a.as_review_row()
    assert row["page"] == 1 and row["bbox"] == [0, 0, 7, 10]
    assert row["quote"]["verify_pass"] == "exact"
    assert [s["method"] for s in row["sources"]] == ["titlepage", "llm_frontier"]
    assert row["sources"][1]["model_id"] == "openai/gpt-5.1"


def test_review_row_without_quote_has_null_location():
    a = AssuredField("f", None, [], False, 0, "unsupported", 0.0, Decision.BLOCK)
    row = a.as_review_row()
    assert row["page"] is None and row["bbox"] is None and row["quote"] is None


# --- Finding ---------------------------------------------------------------- #
def test_finding_row():
    f = Finding(FindingKind.COMPLETENESS, Severity.ERROR, "soa",
                "visit count mismatch", field="visits", expected="8", found="6")
    assert f.as_row() == {"kind": "completeness", "severity": "error", "domain": "soa",
                          "field": "visits", "message": "visit count mismatch",
                          "expected": "8", "found": "6"}


# --- AuditRecord ------------------------------------------------------------ #
def _rec(**kw) -> AuditRecord:
    base = {"run_id": "run1", "event": AuditEvent.EXTRACTION, "source_sha256": "ff" * 32,
            "domain": "metadata", "field": "studyTitle"}
    base.update(kw)
    return AuditRecord(**base)


def test_audit_record_is_frozen_and_gets_identity_defaults():
    r = _rec()
    assert len(r.record_id) == 32
    assert r.timestamp_utc.endswith("+00:00")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.value = "x"  # type: ignore[misc]


def test_audit_record_row_round_trip_with_enums_and_json_columns():
    q = Quote("A Study", VerifyPass.NORMALIZED, page=2, char_start=5, char_end=12,
              bbox=(1.5, 2.0, 30.0, 12.0))
    r = _rec(value="A Study", method=Method.LLM_FRONTIER, decision=Decision.REVIEW,
             confidence=0.71, threshold=0.8, model_id="anthropic/claude-sonnet-4.5",
             prompt_hash="p" * 64, temperature=0.0, seed=7,
             retrieval_config={"shard": "c1.core", "pages": [1, 2]},
             verification={"nli": "supported", "agreement": 1.0}).with_quote(q)
    row = r.to_row()
    assert row["method"] == "llm_frontier" and row["verify_pass"] == "normalized"
    assert isinstance(row["bbox"], str) and isinstance(row["retrieval_config"], str)
    assert set(row) == set(AuditRecord.columns())
    back = AuditRecord.from_row(row)
    assert back == r
    assert back.bbox == (1.5, 2.0, 30.0, 12.0)


def test_audit_record_change_is_a_new_record_not_an_edit():
    first = _rec(value="A Study", decision=Decision.REVIEW)
    edited = replace_fields(first, event=AuditEvent.REVIEW_EDIT, value="A Study of X",
                            prior_value=first.value, reviewer_id="sme@example.org",
                            reason_for_change="title truncated on page 1",
                            record_id="new", timestamp_utc="2026-09-17T00:00:00+00:00")
    assert first.value == "A Study" and first.event is AuditEvent.EXTRACTION
    assert edited.prior_value == "A Study" and edited.record_id != first.record_id


def test_audit_record_from_row_ignores_unknown_columns():
    row = _rec().to_row()
    row["rowid"] = 42
    assert AuditRecord.from_row(row).run_id == "run1"
