"""Assurance ★ (the moat) — turn raw candidates into scored, triaged fields.

4.1 ensemble    — group candidates per field; measure agreement across methods.
4.2 verifier    — check the chosen value is supported by its cited source span.
4.3 confidence  — combine agreement + verifier + coverage into a calibrated score
                  and an auto_accept / review / block decision.

Runs fully WITHOUT an LLM: the deterministic extractors are independent members,
so agreement is real. An LLM, when present, is just an extra member + a stronger
verifier.
"""
from __future__ import annotations

import re
from collections import defaultdict

from usdm4_assure.contracts import AssuredField, Decision, Document, FieldCandidate


def _norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower())


# --- 4.2 grounded verifier -------------------------------------------------- #
def verify(value: str | None, candidates: list[FieldCandidate],
           document: Document) -> str:
    """Is `value` actually supported by a cited source span / the document text?

    Deterministic grounding check: the value's salient tokens must appear in the
    span it was drawn from (or in the document). Catches fabricated values — the
    hallucination guard from DESIGN.md §4.2. With an LLM this becomes a critic call.
    """
    if not value:
        return "unsupported"
    nval = _norm(value)
    spans = _norm(" ".join(c.source_text for c in candidates))
    doctext = _norm(document.full_text)
    if nval and nval in spans:
        return "supported"
    # token overlap fallback (handles minor whitespace/case reflow)
    toks = [t for t in re.split(r"\W+", nval) if len(t) > 2]
    if toks:
        hits = sum(1 for t in toks if t in doctext)
        ratio = hits / len(toks)
        if ratio >= 0.9:
            return "supported"
        if ratio >= 0.5:
            return "partial"
    return "unsupported"


# --- 4.1 ensemble + 4.3 confidence ------------------------------------------ #
def _pick_value(cands: list[FieldCandidate]) -> tuple[str | None, bool]:
    """Choose the consensus value; report whether methods agreed."""
    buckets: dict[str, list[FieldCandidate]] = defaultdict(list)
    for c in cands:
        if c.value:
            buckets[_norm(c.value)].append(c)
    if not buckets:
        return None, False
    # winner = most-supported normalized value
    winner_key = max(buckets, key=lambda k: len(buckets[k]))
    winner = buckets[winner_key][0].value
    distinct_methods = {c.method for c in buckets[winner_key]}
    agree = len(distinct_methods) >= 2 or len(buckets) == 1 and len(cands) >= 2
    return winner, agree


def _confidence(agree: bool, n_methods: int, verifier: str) -> float:
    base = 0.45
    if agree:
        base += 0.30
    base += min(n_methods, 3) * 0.05
    base += {"supported": 0.15, "partial": 0.0, "unsupported": -0.35,
             "n/a": 0.0}[verifier]
    return max(0.0, min(1.0, base))


def _decide(value: str | None, agree: bool, verifier: str,
            conf: float) -> Decision:
    if value is None:
        return Decision.BLOCK
    if verifier == "unsupported":
        return Decision.REVIEW
    if agree and verifier == "supported" and conf >= 0.8:
        return Decision.AUTO_ACCEPT
    return Decision.REVIEW


def assure(candidates: list[FieldCandidate], document: Document,
           fields: list[str]) -> list[AssuredField]:
    by_field: dict[str, list[FieldCandidate]] = defaultdict(list)
    for c in candidates:
        by_field[c.field].append(c)

    results: list[AssuredField] = []
    for f in fields:
        cands = by_field.get(f, [])
        value, agree = _pick_value(cands)
        n_methods = len({c.method for c in cands if c.value})
        v = verify(value, cands, document) if value else "unsupported"
        conf = _confidence(agree, n_methods, v)
        results.append(AssuredField(
            field=f, value=value, candidates=cands,
            methods_agree=agree, n_methods=n_methods,
            verifier=v, confidence=conf, decision=_decide(value, agree, v, conf),
        ))
    return results
