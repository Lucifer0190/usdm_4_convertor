"""Audit store: insert/read round trip and append-only immutability."""
from __future__ import annotations

import sqlite3

import pytest

from usdm4_assure.audit.store import AuditStore, audit_path
from usdm4_assure.audit.writer import write_field_decision, write_run
from usdm4_assure.contracts import (
    AssuredField,
    Decision,
    GroundedCandidate,
    Method,
    Quote,
    VerifyPass,
)
from usdm4_assure.contracts_audit import AuditEvent, AuditRecord


def _store(tmp_path) -> AuditStore:
    return AuditStore(path=tmp_path / "run.sqlite")


def _record(**kw) -> AuditRecord:
    base = {"run_id": "run1", "event": AuditEvent.EXTRACTION,
            "source_sha256": "ab" * 32, "domain": "metadata", "field": "studyTitle"}
    base.update(kw)
    return AuditRecord(**base)


# --- insert / read ----------------------------------------------------------- #
def test_append_and_read_all_round_trips(tmp_path):
    store = _store(tmp_path)
    q = Quote("A Study", VerifyPass.EXACT, page=1, char_start=0, char_end=7, bbox=(0, 0, 7, 10))
    rec = _record(value="A Study", method=Method.LLM_FRONTIER, decision=Decision.AUTO_ACCEPT,
                 confidence=0.93, model_id="anthropic/claude-sonnet-4.5").with_quote(q)
    store.append(rec)

    back = store.read_all()
    assert len(back) == 1
    assert back[0] == rec
    assert len(store) == 1


def test_read_field_filters_and_preserves_insertion_order(tmp_path):
    store = _store(tmp_path)
    r1 = _record(field="studyTitle", value="A")
    r2 = _record(field="studyPhase", value="Phase 2")
    r3 = _record(field="studyTitle", value="A", event=AuditEvent.REVIEW_EDIT,
                prior_value="A", reviewer_id="sme@example.org")
    for r in (r1, r2, r3):
        store.append(r)

    title_history = store.read_field("metadata", "studyTitle")
    assert [r.record_id for r in title_history] == [r1.record_id, r3.record_id]


def test_write_field_decision_pulls_provenance_from_winning_candidate(tmp_path):
    store = _store(tmp_path)
    q = Quote("Northwind Therapeutics", VerifyPass.NORMALIZED, page=1,
             char_start=10, char_end=33, bbox=(1, 2, 3, 4))
    winner = GroundedCandidate("sponsorName", "Northwind Therapeutics", Method.LLM_FRONTIER,
                               q, model_id="openai/gpt-5.1", prompt_hash="deadbeef")
    other = GroundedCandidate("sponsorName", "Northwind", Method.DET_TEXT, None)
    assured = AssuredField("sponsorName", "Northwind Therapeutics", [other, winner],
                           True, 2, "supported", 0.88, Decision.AUTO_ACCEPT)

    rec = write_field_decision(store, run_id="run1", source_sha256="cd" * 32,
                               domain="metadata", assured=assured)

    assert rec.model_id == "openai/gpt-5.1" and rec.prompt_hash == "deadbeef"
    assert rec.method is Method.LLM_FRONTIER
    assert rec.page == 1 and rec.verify_pass is VerifyPass.NORMALIZED
    assert store.read_all() == [rec]


def test_write_run_writes_one_record_per_field(tmp_path):
    store = _store(tmp_path)
    fields = [
        AssuredField("studyTitle", "A Study", [], True, 1, "supported", 0.9, Decision.AUTO_ACCEPT),
        AssuredField("studyPhase", None, [], False, 0, "unsupported", 0.0, Decision.BLOCK),
    ]
    recs = write_run(store, run_id="run1", source_sha256="ef" * 32,
                     domain="metadata", assured_fields=fields)
    assert len(recs) == 2
    assert len(store) == 2
    assert {r.field for r in store.read_all()} == {"studyTitle", "studyPhase"}


# --- append-only immutability ------------------------------------------------ #
def test_store_exposes_no_update_or_delete_method(tmp_path):
    store = _store(tmp_path)
    assert not hasattr(store, "update")
    assert not hasattr(store, "delete")


def test_direct_sql_update_is_rejected_by_trigger(tmp_path):
    store = _store(tmp_path)
    store.append(_record(value="A"))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store._conn.execute(
            "UPDATE audit_records SET value = 'B' WHERE domain = 'metadata'"
        )
    # the row is unchanged
    assert store.read_all()[0].value == "A"


def test_direct_sql_delete_is_rejected_by_trigger(tmp_path):
    store = _store(tmp_path)
    store.append(_record())
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store._conn.execute("DELETE FROM audit_records")
    assert len(store) == 1


def test_a_correction_is_a_new_row_not_a_rewrite(tmp_path):
    store = _store(tmp_path)
    first = _record(value="A Study")
    store.append(first)
    from usdm4_assure.contracts_audit import replace_fields
    edit = replace_fields(first, event=AuditEvent.REVIEW_EDIT, value="A Study of X",
                          prior_value="A Study", reviewer_id="sme@example.org",
                          record_id="edit-1")
    store.append(edit)
    rows = store.read_all()
    assert len(rows) == 2
    assert rows[0].value == "A Study" and rows[1].value == "A Study of X"


# --- path helper -------------------------------------------------------------- #
def test_audit_path_derives_from_sha256(tmp_path):
    p = audit_path("ff" * 32, base_dir=tmp_path)
    assert p == tmp_path / f"{'ff' * 32}.sqlite"


def test_store_requires_path_or_sha256():
    with pytest.raises(ValueError, match="path or source_sha256"):
        AuditStore()
