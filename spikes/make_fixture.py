"""Generate a synthetic clinical protocol PDF with KNOWN ground-truth metadata.

Lets us measure the spine's extraction correctness without a real (large, possibly
sensitive) protocol. Title page mixes labelled fields and a large display title so
both deterministic extraction methods (labels + titlepage) have real signal.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

GROUND_TRUTH = {
    "studyTitle": ("A Phase 2, Randomized, Double-Blind, Placebo-Controlled Study "
                   "of ABC-123 in Adults With Moderate to Severe Plaque Psoriasis"),
    "studyAcronym": "ASCEND-2",
    "sponsorName": "Northwind Therapeutics, Inc.",
    "studyPhase": "Phase 2",
    "protocolIdentifier": "NWT-ABC123-201",
    "studyVersionIdentifier": "2.0",
}

OUT = Path("data/fixtures/protocol_ABC123.pdf")


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BigTitle", parent=styles["Title"], fontSize=20, leading=25)
    label = ParagraphStyle("Lbl", parent=styles["Normal"], fontSize=11, leading=18)

    doc = SimpleDocTemplate(str(OUT), pagesize=letter,
                            title="Clinical Study Protocol")
    story = [
        Spacer(1, 0.6 * inch),
        Paragraph("CLINICAL STUDY PROTOCOL", styles["Heading2"]),
        Spacer(1, 0.3 * inch),
        Paragraph(GROUND_TRUTH["studyTitle"], title_style),
        Spacer(1, 0.5 * inch),
        Paragraph(f"Study Acronym: {GROUND_TRUTH['studyAcronym']}", label),
        Paragraph(f"Sponsor: {GROUND_TRUTH['sponsorName']}", label),
        Paragraph(f"Protocol Number: {GROUND_TRUTH['protocolIdentifier']}", label),
        Paragraph(f"Study Phase: {GROUND_TRUTH['studyPhase']}", label),
        Paragraph(f"Protocol Version: {GROUND_TRUTH['studyVersionIdentifier']}", label),
        Paragraph("Date: 14 August 2026", label),
        Spacer(1, 0.5 * inch),
        Paragraph("Confidential", styles["Italic"]),
    ]
    # A second page of prose so ingest/RAG has non-title content too.
    story += [
        Spacer(1, 0.4 * inch),
        Paragraph("1. SYNOPSIS", styles["Heading2"]),
        Paragraph(
            "This is a Phase 2, randomized, double-blind, placebo-controlled study "
            "evaluating the efficacy and safety of ABC-123 administered "
            "subcutaneously every two weeks in adult participants with moderate to "
            "severe plaque psoriasis. Approximately 240 participants will be "
            "randomized 1:1:1 to ABC-123 low dose, ABC-123 high dose, or placebo.",
            styles["Normal"]),
    ]
    doc.build(story)
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size} bytes)")
    for k, v in GROUND_TRUTH.items():
        print(f"  GT {k}: {v}")
