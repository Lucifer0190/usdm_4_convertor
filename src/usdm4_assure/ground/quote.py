"""The L5 quote resolver — DESIGN.md's "highest-leverage mechanism".

A model (or a deterministic extractor) claims a value came from some text. This
module is the only place that turns that claim into a verified page, character
offset and bounding box:

* **Pass 1 (exact):** the claimed text is a verbatim substring of
  ``Document.text_of(page)``. This is the strong case — no normalization risk.
* **Pass 2 (normalized):** the claimed text matches after collapsing whitespace
  runs (including line breaks, so a quote spanning a paragraph wrap or two
  blocks still resolves), unfolding the ``fi``/``fl`` ligatures, dropping soft
  hyphens, and folding smart quotes/dashes to their ASCII equivalents. The
  *original* characters underneath the match are what get returned — the
  normalization only widens the search, it never substitutes for real geometry.
* **Failure:** the claim has no defensible source. Per DESIGN.md L5 this is a
  **hard, non-probabilistic reject** — callers must not score or auto-accept a
  ``Quote`` whose ``verify_pass`` is ``FAILED``.

Nothing here calls a model. It is pure, deterministic code over
``Document.chars``, which is what makes it classically validatable (the GAMP 5
argument in DESIGN.md L5).
"""
from __future__ import annotations

from usdm4_assure.contracts import Document, Quote, VerifyPass

# fi/fl presentation-form ligatures -> their expanded ASCII letters.
_LIGATURES: dict[str, str] = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
}

# Typographic punctuation -> its plain-ASCII equivalent.
_SMART_PUNCT: dict[str, str] = {
    "‘": "'", "’": "'",          # single quotes
    "“": '"', "”": '"',          # double quotes
    "–": "-", "—": "-",          # en dash, em dash
}

_SOFT_HYPHEN = "­"

# One entry per normalized-output character: the (start, end) span of *original*
# characters it was produced from — the map that lets a normalized match convert
# back into a real ``Document.chars`` range.
_OrigMap = list[tuple[int, int]]


def _normalize(text: str) -> tuple[str, _OrigMap]:
    """Normalize ``text``, returning the result and its origin map.

    ``normalized[i]`` came from ``text[origin[i][0]:origin[i][1]]``. Soft hyphens
    vanish (empty origin span, no output char); a run of whitespace (including
    ``\\n``) collapses to a single space spanning the whole run; a ligature
    expands to multiple output characters that all point back at the one
    original glyph that produced them.
    """
    out: list[str] = []
    origin: _OrigMap = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == _SOFT_HYPHEN:
            i += 1
            continue
        if ch in _LIGATURES:
            for rc in _LIGATURES[ch]:
                out.append(rc)
                origin.append((i, i + 1))
            i += 1
            continue
        if ch in _SMART_PUNCT:
            out.append(_SMART_PUNCT[ch])
            origin.append((i, i + 1))
            i += 1
            continue
        if ch.isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            out.append(" ")
            origin.append((i, j))
            i = j
            continue
        out.append(ch)
        origin.append((i, i + 1))
        i += 1
    return "".join(out), origin


def _resolve_normalized(doc: Document, page: int, text: str) -> Quote | None:
    """Pass 2 for one page: normalized match, converted back to real geometry."""
    norm_query, _ = _normalize(text)
    if not norm_query.strip():
        return None
    norm_page, origin = _normalize(doc.text_of(page))
    idx = norm_page.find(norm_query)
    if idx < 0:
        return None
    end = idx + len(norm_query)
    orig_start = origin[idx][0]
    orig_end = origin[end - 1][1]
    return Quote(text=text, verify_pass=VerifyPass.NORMALIZED, page=page,
                char_start=orig_start, char_end=orig_end,
                bbox=doc.bbox_of(page, orig_start, orig_end))


def resolve_quote(doc: Document, text: str, page: int | None = None) -> Quote:
    """Resolve a claimed quote to verified page geometry, or fail it.

    Args:
        doc: The ingested document (must have ``chars`` populated for any page
            searched — pages without geometry are silently skipped, not
            treated as a match).
        text: The verbatim text a model or extractor claims as its source.
        page: Restrict the search to this page. ``None`` searches every page
            with geometry, preferring an exact match on any page over a
            normalized match on any page (exact pass 1 across all pages runs
            before normalized pass 2 across any page).

    Returns:
        A :class:`~usdm4_assure.contracts.Quote`. ``verify_pass`` is ``EXACT``
        or ``NORMALIZED`` on success; on failure it is ``FAILED`` and every
        location field is ``None`` — treat that as a hard reject, never as a
        low-confidence candidate.
    """
    if not text or not text.strip():
        return Quote.failed(text)

    pages = [page] if page is not None else doc.pages

    # Pass 1: exact substring, checked on every candidate page first so an
    # exact match anywhere outranks a normalized match anywhere.
    for p in pages:
        page_text = doc.text_of(p)
        idx = page_text.find(text)
        if idx >= 0:
            end = idx + len(text)
            return Quote(text=text, verify_pass=VerifyPass.EXACT, page=p,
                        char_start=idx, char_end=end, bbox=doc.bbox_of(p, idx, end))

    # Pass 2: normalized (whitespace collapse incl. newlines, ligatures,
    # soft hyphens, smart punctuation).
    for p in pages:
        resolved = _resolve_normalized(doc, p, text)
        if resolved is not None:
            return resolved

    return Quote.failed(text)
