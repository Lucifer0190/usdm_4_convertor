"""Section graph (task 3.4, L3) — deterministic-first section detection.

Two deterministic sources, both built for every PDF:

* **bookmarks** — the PDF outline (``get_toc``), every level. A bookmark's
  vertical position is taken from the heading block on its target page whose
  text starts with the bookmark title (outline ``to`` points are not
  consistently oriented across producers); no match → top of page.
* **headings** — numbered heading blocks ("5.1 Inclusion Criteria") from
  ingest. Pages carrying many numbered candidates are table-of-contents pages
  and are dropped, as are lines ending in dot leaders or a page number.

Many real protocols carry no usable outline (half the usdm_data corpus), and
some carry a single wrapper bookmark, so the graph keeps whichever source
yields more *typed* sections (ties → bookmarks). The ``route`` role LLM is
consulted only for the untyped residue (:func:`classify_residue`), and its
answer is accepted only if it is a taxonomy label.

A block belongs to the last section that starts at or above it in reading
order (:meth:`SectionGraph.section_for`) — the innermost open section, since
a child heading always follows its parent's.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from usdm4_assure.contracts import Block, Document
from usdm4_assure.llm.base import LLM
from usdm4_assure.sections.classify import Labels, classify_title, resolve, taxonomy
from usdm4_assure.sections.models import DocumentGraphSummary

_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+([A-Za-z(].{1,118})$",
                       re.IGNORECASE)
_APPENDIX = re.compile(r"^(appendix\s+[0-9A-Z]{1,3})\b[.:\s-]*(.{0,110})$", re.IGNORECASE)
_TOC_TAIL = re.compile(r"(?:\.{3,}|…{2,}|\s\d{1,3})\s*$")
_TOC_PAGE_MIN = 6        # numbered candidates on one page ⇒ a ToC page
_MAX_TOP_NUMBER = 30     # "120.5 mg" style table text is not a heading
_TOP_MARGIN = 120.0      # points; a heading below this is mid-page
_MAX_TITLE_WORDS = 14
_RUNNING_HEADER_PAGES = 3  # text on this many pages is page furniture
_LOOKAHEAD = 3        # candidates scanned for a chapter's first subsection


@dataclass(frozen=True)
class Section:
    """One detected section. ``page``/``y`` locate its heading (1-indexed page)."""
    title: str
    number: str
    level: int
    page: int
    y: float
    source: str                   # "bookmark" | "heading"
    labels: Labels = field(default_factory=Labels)
    typed_by: str = "none"        # "rule" | "inherited" | "route" | "none"
    page_end: int | None = None   # last page before the next section starts

    @property
    def section_type(self) -> str | None:
        return self.labels.section_type

    @property
    def section_subtype(self) -> str | None:
        return self.labels.section_subtype

    @property
    def authority_surface(self) -> str | None:
        return self.labels.authority_surface


@dataclass
class SectionGraph:
    """Sections in reading order, plus which source produced them."""
    sections: list[Section]
    source: str                   # "bookmark" | "heading" | "none"

    def section_for(self, page: int, y: float = 0.0) -> Section | None:
        """Innermost section open at ``(page, y)``; ``None`` before the first heading."""
        found = None
        for s in self.sections:
            if (s.page, s.y) <= (page, y + 0.5):
                found = s
            else:
                break
        return found

    def block_section(self, block: Block) -> Section | None:
        return self.section_for(block.page, block.bbox[1])

    @property
    def typed_fraction(self) -> float:
        if not self.sections:
            return 0.0
        return sum(s.labels.typed for s in self.sections) / len(self.sections)

    def untyped(self) -> list[Section]:
        return [s for s in self.sections if not s.labels.typed]

    def summary(self, document_id: int = 0, page_count: int = 0) -> DocumentGraphSummary:
        def counts(values) -> dict[str, int]:
            return dict(Counter(v for v in values if v))
        return DocumentGraphSummary(
            document_id=document_id, chunk_count=len(self.sections), page_count=page_count,
            section_type_counts=counts(s.section_type for s in self.sections),
            section_subtype_counts=counts(s.section_subtype for s in self.sections),
            authority_surface_counts=counts(s.authority_surface for s in self.sections),
            amendment_chunk_count=sum(s.section_subtype == "amendment_history"
                                      for s in self.sections),
            appendix_chunk_count=sum(s.section_type == "appendix" for s in self.sections),
        )


# --- building --------------------------------------------------------------- #
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_number(title: str) -> tuple[str, str]:
    m = _NUMBERED.match(title)
    return (m.group(1), m.group(2).strip()) if m else ("", title)


def _labelled(raw: list[Section]) -> list[Section]:
    """Sort into reading order, classify, and resolve inheritance by level."""
    raw = sorted(raw, key=lambda s: (s.page, s.y))
    out: list[Section] = []
    stack: list[Section] = []     # open ancestors, strictly increasing level
    for s in raw:
        while stack and stack[-1].level >= s.level:
            stack.pop()
        parent = stack[-1].labels if stack else None
        own = classify_title(s.title)
        labels = resolve(own, parent)
        typed_by = "rule" if own.typed else ("inherited" if labels.typed else "none")
        s = replace(s, labels=labels, typed_by=typed_by)
        out.append(s)
        stack.append(s)
    for i in range(len(out) - 1):
        nxt = out[i + 1]
        # A next heading well down its page means this section runs onto that page.
        end = nxt.page if nxt.y > _TOP_MARGIN else nxt.page - 1
        out[i] = replace(out[i], page_end=max(out[i].page, end))
    return out


def _title_shaped(title: str) -> bool:
    """Heading titles are short labels, not sentences or numbered list items.

    Rejects the two false positives seen on real protocols: numbered
    amendment-summary bullets ("4 Section 1.4 Study Design: text updated for
    clarity.") and numbered eligibility criteria ("1 Provision of informed
    consent prior to any study specific procedures").
    """
    if not title[:1].isupper() or title.rstrip()[-1:] in ".;,:":
        return False
    if len(title.split()) > _MAX_TITLE_WORDS or not re.search(r"[A-Za-z]{3}", title):
        return False
    return sum(ch.isdigit() for ch in title) <= len(title) // 4


def _has_subsection(num: str, following: list[tuple[Block, str, str, int]]) -> bool:
    return any(n.startswith(f"{num}.") for _, n, _, _ in following)


def from_headings(doc: Document) -> list[Section]:
    """Numbered / "Appendix N" heading blocks, ToC pages excluded.

    Section numbers only move forward in a protocol body. A candidate whose
    number goes *backwards* (a list restarting at "1" inside section 5, a
    cross-reference to "3.1" in prose) is kept only if ingest classified it as
    a heading-font block — which is what lets the real "1 INTRODUCTION" after
    a table of contents reset the sequence. A body-font single-number
    candidate ("4 Documented BRCA status") is a list item unless a real
    chapter follows it: an "N.x" subsection within the next few candidates.

    Unnumbered headings ("PROTOCOL AMENDMENT SUMMARY OF CHANGES", "SYNOPSIS")
    are kept only when heading-font or upper-case, recognised by a taxonomy
    rule, and not repeated on several pages — a running header such as
    "Protocol Amendment 3" must not open a section on every page. They nest
    one level under the current numbered section (level 1 in front matter).
    """
    pages_of: dict[str, set[int]] = {}
    for b in doc.blocks:
        pages_of.setdefault(_norm(b.text), set()).add(b.page)

    cands: list[tuple[Block, str, str, int]] = []
    level_now = 0
    for b in doc.blocks:
        text = _norm(b.text)
        if len(text) > 120 or _TOC_TAIL.search(text):
            continue
        m = _NUMBERED.match(text)
        if m:
            number, title = m.group(1), m.group(2).strip()
            if int(number.split(".")[0]) <= _MAX_TOP_NUMBER and _title_shaped(title):
                level_now = number.count(".") + 1
                cands.append((b, number, title, level_now))
            continue
        m = _APPENDIX.match(text)
        if m and (b.kind == "heading" or text.isupper() or len(text) < 80):
            level_now = 1
            cands.append((b, "", text, 1))
            continue
        if ((b.kind == "heading" or (text.isupper() and len(text.split()) <= 10))
                and _title_shaped(text) and len(pages_of[text]) < _RUNNING_HEADER_PAGES
                and classify_title(text).typed):
            cands.append((b, "", text, level_now + 1))
    per_page = Counter(c[0].page for c in cands)
    toc_pages = {p for p, n in per_page.items() if n >= _TOC_PAGE_MIN}

    cands = [c for c in cands if c[0].page not in toc_pages]
    out: list[Section] = []
    prev: tuple[int, ...] = ()
    for i, (b, num, title, level) in enumerate(cands):
        if num:
            parts = tuple(int(x) for x in num.split("."))
            if parts <= prev and b.kind != "heading":
                continue
            if (len(parts) == 1 and b.kind != "heading" and not title.isupper()
                    and not _has_subsection(num, cands[i + 1:i + 1 + _LOOKAHEAD])):
                continue
            prev = parts
        out.append(Section(title=f"{num} {title}" if num else title, number=num,
                           level=level, page=b.page, y=b.bbox[1], source="heading"))
    return out


def from_bookmarks(pdf_path: str | Path, doc: Document) -> list[Section]:
    """Every outline entry with a valid target page, positioned on its heading block."""
    import pymupdf
    with pymupdf.open(pdf_path) as pdf:
        toc = pdf.get_toc(simple=True)
    by_page: dict[int, list[Block]] = {}
    for b in doc.blocks:
        by_page.setdefault(b.page, []).append(b)
    out: list[Section] = []
    for level, raw_title, page in toc:
        title = _norm(raw_title.replace("\r", " "))
        if page < 1 or not title:
            continue
        key = title.lower()[:25]
        y = next((b.bbox[1] for b in by_page.get(page, [])
                  if _norm(b.text).lower().startswith(key)), 0.0)
        # The outline is already in reading order: an entry with no matching
        # heading block must not sort above its predecessor on the same page.
        if out and out[-1].page == page:
            y = max(y, out[-1].y)
        number, _ = _split_number(title)
        out.append(Section(title=title, number=number, level=level, page=page, y=y,
                           source="bookmark"))
    return out


def build_graph(doc: Document, pdf_path: str | Path | None = None) -> SectionGraph:
    """Deterministic section graph: the better-typed of bookmarks vs headings."""
    options: list[tuple[str, list[Section]]] = []
    if pdf_path is not None:
        options.append(("bookmark", _labelled(from_bookmarks(pdf_path, doc))))
    options.append(("heading", _labelled(from_headings(doc))))
    source, sections = max(options, key=lambda o: sum(s.labels.typed for s in o[1]))
    if not sections:
        return SectionGraph([], "none")
    return SectionGraph(sections, source)


# --- route-role residue ------------------------------------------------------ #
_ROUTE_PROMPT = (
    "Classify this clinical-protocol section heading into exactly one of: {labels}.\n"
    "If none fits, answer none. Answer with the single label only.\n\nHeading: {title}\n"
    "Parent heading: {parent}")


def classify_residue(graph: SectionGraph, llm: LLM | None) -> SectionGraph:
    """Ask the ``route`` role for untyped sections only; accept taxonomy labels only.

    Children of a newly typed section re-inherit on the next :func:`build_graph`
    call, not here — this pass never overrides a deterministic label.
    """
    if llm is None or not getattr(llm, "available", False) or not graph.untyped():
        return graph
    allowed = taxonomy()["canonical_section_type"]
    out = []
    for i, s in enumerate(graph.sections):
        if s.labels.typed:
            out.append(s)
            continue
        parent = next((p.title for p in reversed(graph.sections[:i]) if p.level < s.level), "")
        answer = llm.complete(_ROUTE_PROMPT.format(labels=", ".join(allowed), title=s.title,
                                                   parent=parent or "(none)"),
                              task="classify", max_tokens=16).strip().lower().strip(".\"' ")
        if answer in allowed:
            s = replace(s, labels=Labels(answer, None, "content_section"), typed_by="route")
        out.append(s)
    return SectionGraph(out, graph.source)
