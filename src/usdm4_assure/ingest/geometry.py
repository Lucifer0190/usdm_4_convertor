"""Character-level geometry — the substrate the L5 quote resolver runs on.

DESIGN.md L5: the model never emits coordinates; we resolve them ourselves from
the PDF's own text layer. PyMuPDF's ``page.get_text("rawdict")`` exposes one
bbox per glyph, which is the finest granularity available without re-rendering,
so :func:`page_geometry` walks it directly (bypassing the coarser block/line/span
text already used for :class:`~usdm4_assure.contracts.Block`) and returns a page's
text together with one :class:`~usdm4_assure.contracts.CharSpan` per character in
that text, in order. The invariant this buys is simple and load-bearing:
``text[i]`` and ``chars[i]`` describe the same glyph, so any substring match in
``text`` converts directly into a bbox via ``chars[start:end]``.

Block boundaries become a literal ``"\\n"`` and span boundaries within a block
become a literal ``" "`` (mirroring how :mod:`usdm4_assure.ingest.pdf` already
joins spans/blocks for :attr:`Document.full_text`), each represented by a
zero-width synthetic :class:`CharSpan` positioned at the preceding glyph's right
edge so it never distorts a real bbox union.
"""
from __future__ import annotations

from usdm4_assure.contracts import BBox, CharSpan

# Bbox for a synthetic separator char with nothing before it on the page yet.
_ORIGIN_BBOX: BBox = (0.0, 0.0, 0.0, 0.0)


def _separator_bbox(chars: list[CharSpan]) -> BBox:
    """A zero-width box at the previous glyph's right edge (or the page origin)."""
    if not chars:
        return _ORIGIN_BBOX
    _x0, y0, x1, y1 = chars[-1].bbox
    return (x1, y0, x1, y1)


def page_geometry(page, page_no: int) -> tuple[str, list[CharSpan]]:
    """Char-level text and geometry for one PyMuPDF page.

    Args:
        page: A ``pymupdf.Page`` (already open; not closed here).
        page_no: 1-indexed page number, stamped onto every ``CharSpan``.

    Returns:
        ``(text, chars)`` where ``text == "".join(c.char for c in chars)`` and
        ``chars[i].bbox`` is that character's PDF-space bounding box. Image-only
        blocks (no ``lines``) contribute nothing.
    """
    rawdict = page.get_text("rawdict")
    chars: list[CharSpan] = []
    started_block = False

    for blk in rawdict.get("blocks", []):
        lines = blk.get("lines", [])
        if not lines:
            continue  # image or other non-text block
        if started_block:
            chars.append(CharSpan("\n", page_no, _separator_bbox(chars)))
        started_block = True

        started_span = False
        for line in lines:
            for span in line.get("spans", []):
                if started_span:
                    chars.append(CharSpan(" ", page_no, _separator_bbox(chars)))
                started_span = True
                for ch in span.get("chars", []):
                    chars.append(CharSpan(ch["c"], page_no, tuple(ch["bbox"])))

    text = "".join(c.char for c in chars)
    return text, chars
