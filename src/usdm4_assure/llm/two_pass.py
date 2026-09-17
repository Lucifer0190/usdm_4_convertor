"""Two-pass sharded LLM extraction (DESIGN.md L4/L5).

Every field an LLM proposes must carry a verbatim quote, and the quote is
resolved to page geometry by :mod:`usdm4_assure.ground.quote` — never trusted
from the model's own coordinates. Two calls per shard:

1. **Reasoning pass** — free text. The model is asked to locate and quote its
   evidence for each field in prose, before committing to a structured answer.
   This pass is not parsed; it exists to let the model "show its work" before
   the constrained pass, which published evidence associates with fewer
   fabricated values than a single-shot JSON extraction.
2. **JSON pass** — given its own reasoning as context, the model returns
   strict JSON: one ``{field, value, quote}`` object per field in the shard.
   ``quote`` is then resolved against the document; a quote that fails to
   resolve produces a :class:`~usdm4_assure.contracts.GroundedCandidate` whose
   ``quote.verify_pass`` is ``FAILED`` — callers must treat that as ungrounded
   (DESIGN.md L5's hard reject), not as a low-confidence value.

Prompt templates live in ``llm/prompts/<shard.id>.pass{1,2}.md`` and are
loaded verbatim, so editing a template changes that shard's ``prompt_hash``
(sha256 of both templates) — exactly what the Part 11 audit trail needs to
reproduce a call.
"""
from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path

from usdm4_assure.contracts import Document, GroundedCandidate, Method
from usdm4_assure.extract.shards import Shard
from usdm4_assure.ground.quote import resolve_quote
from usdm4_assure.llm.base import LLM

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# How much of the document each pass sees. Generous enough for a real protocol
# section; bounded so a large PDF doesn't blow the model's context.
_MAX_DOC_CHARS = 12000


@cache
def _load_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _pass_names(shard: Shard) -> tuple[str, str]:
    return f"{shard.id}.pass1.md", f"{shard.id}.pass2.md"


def prompt_hash(shard: Shard) -> str:
    """A stable hash of a shard's two prompt templates.

    Depends only on the template *files* on disk, not on any document or
    model — two calls against the same shard on different protocols get the
    same hash, and editing a template (a new prompt "version") changes it.
    This is the ``prompt_hash`` recorded in every :class:`AuditRecord`.
    """
    p1_name, p2_name = _pass_names(shard)
    payload = shard.id + "\x00" + _load_template(p1_name) + "\x00" + _load_template(p2_name)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fill(template: str, **values: str) -> str:
    """Substitute ``{name}`` placeholders via plain replace (not ``str.format``,
    so the JSON braces inside a template never need escaping)."""
    out = template
    for key, val in values.items():
        out = out.replace("{" + key + "}", val)
    return out


def _parse_json_items(raw: str) -> list[dict]:
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON array found in model output")
    return json.loads(raw[start:end + 1])


def extract_shard(doc: Document, llm: LLM, shard: Shard) -> list[GroundedCandidate]:
    """Run one shard's two-pass extraction against ``doc`` with ``llm``.

    Returns:
        One :class:`GroundedCandidate` per field the model returned a
        non-null value for. ``[]`` if the LLM is unavailable or either pass
        fails to produce parseable output — a bad LLM member must not crash
        the run (mirrors the existing single-pass ``extract_llm`` behavior).
    """
    if not getattr(llm, "available", False):
        return []

    p1_name, p2_name = _pass_names(shard)
    phash = prompt_hash(shard)
    fields_str = ", ".join(shard.fields)
    text = doc.full_text[:_MAX_DOC_CHARS]

    try:
        pass1_prompt = _fill(_load_template(p1_name), description=shard.description,
                             fields=fields_str, document_text=text)
        reasoning = llm.complete(pass1_prompt, task="extract_prose", max_tokens=800)

        pass2_prompt = _fill(_load_template(p2_name), fields=fields_str,
                             reasoning=reasoning, document_text=text)
        raw = llm.complete(pass2_prompt, task="extract_prose", max_tokens=1200)
        items = _parse_json_items(raw)
    except Exception:  # noqa: BLE001 — a bad LLM member must not crash the run
        return []

    model_id = getattr(llm, "model", None) or getattr(llm, "name", None)
    out: list[GroundedCandidate] = []
    valid_fields = set(shard.fields)
    for item in items:
        if not isinstance(item, dict):
            continue
        field_name = item.get("field")
        value = item.get("value")
        if field_name not in valid_fields or not value:
            continue
        quote_text = item.get("quote") or ""
        quote = resolve_quote(doc, quote_text) if quote_text else None
        out.append(GroundedCandidate(
            field=field_name, value=str(value).strip(), method=Method.LLM_FRONTIER,
            quote=quote, model_id=model_id, prompt_hash=phash, domain=shard.domain,
        ))
    return out


def extract_domain(doc: Document, llm: LLM, shards: list[Shard]) -> list[GroundedCandidate]:
    """Run every shard for a domain and concatenate their candidates."""
    out: list[GroundedCandidate] = []
    for shard in shards:
        out += extract_shard(doc, llm, shard)
    return out
