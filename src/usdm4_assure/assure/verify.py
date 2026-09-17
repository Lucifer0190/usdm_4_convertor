"""L6 — the grounded verifier: does the source text actually support the value?

Two tiers, in the order DESIGN.md L6 describes:

1. **Deterministic token overlap** (:func:`verify_deterministic`) — always
   runs, free. Checks the value's salient tokens against its supporting text
   (a resolved ``Quote``'s text for a grounded candidate, else the legacy
   free-text span / document fallback for one that isn't). Catches
   fabricated values without a model call.
2. **LLM escalation** (:func:`verify_llm`) — DESIGN.md L6: cross-family
   (the ``verify`` role, never the extractor judging itself), on the
   *uncertain subset only*. Called only when the deterministic pass returns
   ``"partial"`` (genuinely ambiguous) and a model is available; asks a
   strict entailment question and is not allowed to use outside knowledge.

Note that quote *grounding* (does this text appear verbatim on the page) and
quote *verification* (does this text actually support the value) are
different checks — a quote can resolve perfectly and still not support the
value it was attached to. Grounding is enforced in
:mod:`usdm4_assure.assure` before this module ever runs; this module answers
the second question.
"""
from __future__ import annotations

import re

from usdm4_assure.llm.base import LLM


def _norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower())


def verify_deterministic(value: str | None, source_text: str, document_text: str) -> str:
    """Token-overlap grounding check.

    Args:
        value: The proposed value.
        source_text: The best available supporting text (a resolved quote,
            or a legacy candidate's free-text span).
        document_text: The whole document, as a fallback when ``source_text``
            is thin (e.g. a short label match).

    Returns:
        ``"supported"`` | ``"partial"`` | ``"unsupported"``.
    """
    if not value:
        return "unsupported"
    nval = _norm(value)
    span = _norm(source_text)
    doctext = _norm(document_text)
    if nval and nval in span:
        return "supported"
    toks = [t for t in re.split(r"\W+", nval) if len(t) > 2]
    if not toks:
        return "unsupported"
    hits = sum(1 for t in toks if t in doctext)
    ratio = hits / len(toks)
    if ratio >= 0.9:
        return "supported"
    if ratio >= 0.5:
        return "partial"
    return "unsupported"


_VERIFY_SYSTEM = (
    "You check whether a QUOTE from a clinical trial protocol supports a proposed "
    "VALUE. Answer with exactly one word: 'supported' if the quote clearly states or "
    "directly implies the value, 'partial' if related but not conclusive, or "
    "'unsupported' if the quote does not support the value. Never use outside "
    "knowledge; judge only the quote text given."
)


def verify_llm(value: str, quote_text: str, llm: LLM) -> str:
    """Escalate one uncertain field to the ``verify``-role model.

    Args:
        value: The proposed value.
        quote_text: The (grounded) quote text to judge it against.
        llm: A model member. If unavailable, the escalation is skipped.

    Returns:
        ``"supported"`` | ``"partial"`` | ``"unsupported"`` — falls back to
        ``"partial"`` (the deterministic verdict this is escalating from) on
        an unavailable model, a call failure, or an unparseable reply, since
        escalation exists to *resolve* ambiguity, never to manufacture false
        confidence.
    """
    if not getattr(llm, "available", False) or not quote_text:
        return "partial"
    prompt = f"QUOTE:\n{quote_text}\n\nVALUE:\n{value}\n\nAnswer now."
    try:
        raw = llm.complete(prompt, task="verify", system=_VERIFY_SYSTEM, max_tokens=10)
    except Exception:  # noqa: BLE001 — a bad verifier must not crash the run
        return "partial"
    verdict = raw.strip().lower()
    for label in ("supported", "unsupported", "partial"):
        if label in verdict:
            return label
    return "partial"
