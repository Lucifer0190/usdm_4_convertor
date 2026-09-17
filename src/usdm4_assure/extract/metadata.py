"""Extraction C1 — study metadata.

Provides multiple INDEPENDENT extraction methods so the Assurance layer has a
real agreement signal:
  * labels    — deterministic, label-driven regex ("Protocol Title:", ...)
  * titlepage — deterministic, layout heuristics over page-1 blocks
  * claude    — LLM member, included only when a key is present

Fields (subset of USDM StudyVersion metadata):
  studyTitle, studyAcronym, sponsorName, studyPhase,
  protocolIdentifier, studyVersionIdentifier
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable

from usdm4_assure.contracts import Document, FieldCandidate, GroundedCandidate
from usdm4_assure.llm.base import LLM

FIELDS = [
    "studyTitle", "studyAcronym", "sponsorName",
    "studyPhase", "protocolIdentifier", "studyVersionIdentifier",
]

_LABELS: dict[str, list[str]] = {
    "studyTitle": [r"protocol title", r"study title", r"full title", r"title of study"],
    "studyAcronym": [r"acronym", r"short title"],
    "sponsorName": [r"sponsor", r"sponsor name"],
    "studyPhase": [r"study phase", r"phase of study", r"trial phase", r"phase"],
    "protocolIdentifier": [r"protocol number", r"protocol no\.?", r"protocol id",
                           r"sponsor protocol number", r"eudract"],
    "studyVersionIdentifier": [r"protocol version", r"version number", r"amendment number",
                               r"version"],
}

_PHASE_RE = re.compile(
    r"\bphase\s*(?:0|i{1,3}v?|iv|[1-4])(?:\s*[/-]\s*(?:i{1,3}v?|[1-4]))?\b", re.IGNORECASE)


def _label_value(line: str) -> str | None:
    """Return the value part after a 'Label: value' colon, if any."""
    if ":" in line:
        val = line.split(":", 1)[1].strip()
        return val or None
    return None


def extract_labels(doc: Document) -> list[FieldCandidate]:
    out: list[FieldCandidate] = []
    lines = [(b.page, ln.strip())
             for b in doc.blocks if b.page <= 3
             for ln in b.text.splitlines() if ln.strip()]
    for field_name, patterns in _LABELS.items():
        for page, line in lines:
            low = line.lower()
            if any(re.search(rf"\b{p}\b", low) for p in patterns):
                val = _label_value(line)
                if field_name == "studyPhase":
                    m = _PHASE_RE.search(line)
                    val = m.group(0) if m else val
                if val and 1 <= len(val) <= 300:
                    out.append(FieldCandidate(
                        field=field_name, value=val, method="labels",
                        source_text=line, source_page=page))
                    break  # first labelled hit wins for this method
    return out


def extract_titlepage(doc: Document) -> list[FieldCandidate]:
    """Independent path: infer from page-1 layout, not labels."""
    out: list[FieldCandidate] = []
    p1 = [b for b in doc.blocks if b.page == 1]

    # Title = the longest heading-kind block on page 1 (title pages set it large).
    headings = [b for b in p1 if b.kind == "heading" and len(b.text) > 12]
    if headings:
        title_blk = max(headings, key=lambda b: len(b.text))
        out.append(FieldCandidate("studyTitle", title_blk.text.strip(),
                                  "titlepage", title_blk.text, 1))

    joined = "\n".join(b.text for b in p1)
    m = _PHASE_RE.search(joined)
    if m:
        out.append(FieldCandidate("studyPhase", m.group(0), "titlepage",
                                  m.group(0), 1))
    # Identifier-shaped tokens (e.g. ABC-1234, XYZ1840-WD-204).
    idm = re.search(r"\b[A-Z]{2,}[A-Z0-9]*-?\d{2,}(?:-[A-Z0-9]+)*\b", joined)
    if idm:
        out.append(FieldCandidate("protocolIdentifier", idm.group(0), "titlepage",
                                  idm.group(0), 1))
    return out


_LLM_SYSTEM = (
    "You extract study metadata from clinical trial protocol text. "
    "Return ONLY strict JSON with keys: "
    "studyTitle, studyAcronym, sponsorName, studyPhase, protocolIdentifier, "
    "studyVersionIdentifier. Use null for any field not clearly present. "
    "Copy values verbatim from the text; never infer or invent."
)


def extract_llm(doc: Document, llm: LLM) -> list[FieldCandidate]:
    """Extract metadata with one LLM member; tag candidates with ``llm.name``.

    Works for any model behind the ``LLM`` interface — Claude, an SLM, etc. — so a
    small model (e.g. Llama 3.1 8B) can be added as an independent ensemble member
    of a *different family* than Claude, which strengthens the agreement signal.

    Args:
        doc: The ingested protocol document.
        llm: The model member. If ``llm.available`` is false, returns ``[]``.

    Returns:
        One ``FieldCandidate`` per field the model returned, tagged ``llm.name``.
    """
    if not getattr(llm, "available", False):
        return []
    head = doc.head_text(3)[:8000]
    prompt = f"PROTOCOL TEXT (first pages):\n{head}\n\nReturn the JSON now."
    try:
        raw = llm.complete(prompt, task="extract_metadata", system=_LLM_SYSTEM,
                           max_tokens=800)
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:  # noqa: BLE001 — a bad LLM member must not crash the run
        return []
    out: list[FieldCandidate] = []
    for f in FIELDS:
        v = data.get(f)
        if v:
            out.append(FieldCandidate(f, str(v).strip(), getattr(llm, "name", "llm"),
                                      source_text=str(v), source_page=1))
    return out


# Back-compat alias.
extract_claude = extract_llm


def extract_llm_grounded(doc: Document, llm: LLM) -> list[GroundedCandidate]:
    """Two-pass, quote-grounded metadata extraction (DESIGN.md L4/L5).

    Replaces :func:`extract_llm`'s single-shot JSON call with a reasoning
    pass followed by a JSON pass whose every value must carry a verbatim
    quote, resolved against ``doc`` — never a model-emitted coordinate. See
    :mod:`usdm4_assure.llm.two_pass` for the shard mechanics.

    Args:
        doc: The ingested protocol document.
        llm: The model member. Returns ``[]`` if unavailable.

    Returns:
        One ``GroundedCandidate`` per field the model returned a value for;
        a candidate whose ``quote.verify_pass`` is ``FAILED`` is ungrounded
        and must not be auto-accepted.
    """
    from usdm4_assure.extract.shards import SHARD_C1_METADATA
    from usdm4_assure.llm.two_pass import extract_shard
    return extract_shard(doc, llm, SHARD_C1_METADATA)


def extract_all(doc: Document, llms: LLM | Iterable[LLM]) -> list[FieldCandidate]:
    """Run the deterministic methods plus every provided LLM member.

    Args:
        doc: The ingested protocol document.
        llms: A single ``LLM`` or an iterable of them (e.g. Claude + an SLM). Each
            available member contributes an independent set of candidates; the
            Assurance layer reconciles them.

    Returns:
        All ``FieldCandidate``s from every method, ready for ``assure.assure``.
    """
    members = [llms] if isinstance(llms, LLM) else list(llms)
    cands = extract_labels(doc) + extract_titlepage(doc)
    for member in members:
        cands += extract_llm(doc, member)
    return cands
