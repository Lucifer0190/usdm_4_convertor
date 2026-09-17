"""Shard definitions, prompt hash stability, and two-pass JSON parsing."""
from __future__ import annotations

from pathlib import Path

import pytest

from usdm4_assure.contracts import CharSpan, Document, Method, VerifyPass
from usdm4_assure.extract.shards import (
    ALL_SHARDS,
    MAX_SHARD_FIELDS,
    SHARD_C1_METADATA,
    SHARDS_BY_DOMAIN,
    Shard,
)
from usdm4_assure.llm.two_pass import extract_shard, prompt_hash


def _doc(text: str, page: int = 1) -> Document:
    chars = [CharSpan(ch, page, (float(i), 0.0, float(i + 1), 10.0))
             for i, ch in enumerate(text)]
    return Document(source=Path("x.pdf"), blocks=[], full_text=text, chars={page: chars})


class _StubLLM:
    """A canned two-call LLM: first call returns ``reasoning``, second ``json_reply``."""

    def __init__(self, reasoning: str, json_reply: str, available: bool = True):
        self.reasoning = reasoning
        self.json_reply = json_reply
        self.available = available
        self.name = "stub"
        self.model = "stub/test-model"
        self.calls: list[str] = []

    def complete(self, prompt, *, task="extract_prose", system=None, max_tokens=1024):
        self.calls.append(prompt)
        return self.reasoning if len(self.calls) == 1 else self.json_reply


# --- shard sizes -------------------------------------------------------------- #
def test_every_shard_is_under_the_field_ceiling():
    for shard in ALL_SHARDS:
        assert 0 < len(shard.fields) <= MAX_SHARD_FIELDS


def test_shard_rejects_too_many_fields():
    with pytest.raises(ValueError, match="exceeding"):
        Shard(id="x", domain="x", fields=[f"f{i}" for i in range(MAX_SHARD_FIELDS + 1)])


def test_shard_rejects_no_fields():
    with pytest.raises(ValueError, match="no fields"):
        Shard(id="x", domain="x", fields=[])


def test_shards_by_domain_groups_correctly():
    assert {s.domain for s in ALL_SHARDS} == set(SHARDS_BY_DOMAIN)
    for domain, shards in SHARDS_BY_DOMAIN.items():
        assert all(s.domain == domain for s in shards)


# --- prompt hash stability ---------------------------------------------------- #
def test_prompt_hash_is_stable_across_calls():
    h1 = prompt_hash(SHARD_C1_METADATA)
    h2 = prompt_hash(SHARD_C1_METADATA)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_prompt_hash_is_independent_of_the_document():
    # prompt_hash depends only on the templates + shard id, never the doc.
    assert prompt_hash(SHARD_C1_METADATA) == prompt_hash(SHARD_C1_METADATA)


def test_prompt_hash_differs_across_shards():
    hashes = {s.id: prompt_hash(s) for s in ALL_SHARDS}
    assert len(set(hashes.values())) == len(hashes)


# --- two-pass JSON parsing with a stub LLM ------------------------------------ #
def test_extract_shard_produces_grounded_candidates():
    doc = _doc("Protocol Title: A Study of ABC-123. Sponsor: Northwind Therapeutics.")
    reply = (
        '[{"field": "studyTitle", "value": "A Study of ABC-123", '
        '"quote": "A Study of ABC-123"},'
        '{"field": "sponsorName", "value": "Northwind Therapeutics", '
        '"quote": "Northwind Therapeutics"},'
        '{"field": "studyPhase", "value": null, "quote": ""}]'
    )
    llm = _StubLLM(reasoning="I found the title and sponsor.", json_reply=reply)

    cands = extract_shard(doc, llm, SHARD_C1_METADATA)

    by_field = {c.field: c for c in cands}
    assert set(by_field) == {"studyTitle", "sponsorName"}  # null value dropped
    assert by_field["studyTitle"].quote.verify_pass is VerifyPass.EXACT
    assert by_field["studyTitle"].method is Method.LLM_FRONTIER
    assert by_field["studyTitle"].model_id == "stub/test-model"
    assert by_field["studyTitle"].prompt_hash == prompt_hash(SHARD_C1_METADATA)
    assert len(llm.calls) == 2  # reasoning pass, then JSON pass


def test_extract_shard_fabricated_quote_is_ungrounded():
    doc = _doc("Protocol Title: A Study of ABC-123.")
    reply = ('[{"field": "studyTitle", "value": "A Study of ABC-123", '
             '"quote": "this text does not appear anywhere in the document"}]')
    llm = _StubLLM(reasoning="...", json_reply=reply)

    cands = extract_shard(doc, llm, SHARD_C1_METADATA)

    assert len(cands) == 1
    assert not cands[0].grounded
    assert cands[0].quote.verify_pass is VerifyPass.FAILED


def test_extract_shard_ignores_fields_outside_the_shard():
    doc = _doc("Protocol Title: A Study.")
    reply = ('[{"field": "studyTitle", "value": "A Study", "quote": "A Study"},'
             '{"field": "notARealField", "value": "x", "quote": "x"}]')
    llm = _StubLLM(reasoning="...", json_reply=reply)

    cands = extract_shard(doc, llm, SHARD_C1_METADATA)

    assert {c.field for c in cands} == {"studyTitle"}


def test_extract_shard_bad_json_returns_empty_not_raise():
    doc = _doc("Protocol Title: A Study.")
    llm = _StubLLM(reasoning="...", json_reply="not json at all")
    assert extract_shard(doc, llm, SHARD_C1_METADATA) == []


def test_extract_shard_unavailable_llm_returns_empty_without_calling():
    doc = _doc("Protocol Title: A Study.")
    llm = _StubLLM(reasoning="...", json_reply="[]", available=False)
    assert extract_shard(doc, llm, SHARD_C1_METADATA) == []
    assert llm.calls == []
