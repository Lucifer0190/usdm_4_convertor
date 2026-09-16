"""A complete synthetic protocol: title page + synopsis (arms) + SoA table.

One PDF that exercises the whole pipeline — metadata (C1), design skeleton (C2),
and Schedule of Activities — so we can assemble ONE conformant USDM 4.0 study
and check it against a single ground truth.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
)

OUT = Path("data/fixtures/protocol_full.pdf")

GROUND_TRUTH = {
    "studyTitle": ("A Phase 2, Randomized, Double-Blind, Placebo-Controlled Study "
                   "of ABC-123 in Adults With Moderate to Severe Plaque Psoriasis"),
    "studyAcronym": "ASCEND-2",
    "sponsorName": "Northwind Therapeutics, Inc.",
    "studyPhase": "Phase 2",
    "protocolIdentifier": "NWT-ABC123-201",
    "studyVersionIdentifier": "2.0",
    "interventionModel": "Parallel",
    "arms": [
        {"name": "ABC-123 Low Dose", "type": "Experimental"},
        {"name": "ABC-123 High Dose", "type": "Experimental"},
        {"name": "Placebo", "type": "Placebo Comparator"},
    ],
    "age_min": 18, "age_max": 75, "sex": "ALL",
    "inclusion": [
        "Adults aged 18 to 75 years at screening.",
        "Diagnosis of moderate to severe plaque psoriasis for at least 6 months.",
        "Body surface area involvement of at least 10 percent.",
    ],
    "exclusion": [
        "Pregnant or breastfeeding women.",
        "History of active tuberculosis.",
        "Use of any biologic therapy within 12 weeks of screening.",
    ],
    "primaryObjective": ("To evaluate the efficacy of ABC-123 compared with placebo "
                         "on the proportion of participants achieving PASI 75 at Week 12."),
    "primaryEndpoint": ("Proportion of participants achieving a 75 percent reduction in "
                        "PASI score (PASI 75) at Week 12."),
    # SoA
    "epochs": ["Screening", "Treatment", "Treatment", "Treatment", "Follow-up"],
    "visits": ["V1", "V2", "V3", "V4", "V5"],
    "timings": ["Day -14", "Day 1", "Week 4", "Week 8", "Week 12"],
    "activities": ["Informed Consent", "Vital Signs", "ECG", "Blood Chemistry",
                   "PK Sample"],
    "marks": {
        "Informed Consent": [0], "Vital Signs": [0, 1, 2, 3, 4],
        "ECG": [0, 1, 3], "Blood Chemistry": [0, 1, 2, 3, 4], "PK Sample": [1, 2],
    },
    "footnote_activity": "PK Sample",
}


def ground_truth() -> dict:
    return GROUND_TRUTH


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    big = ParagraphStyle("BigTitle", parent=styles["Title"], fontSize=20, leading=25)
    lbl = ParagraphStyle("Lbl", parent=styles["Normal"], fontSize=11, leading=18)
    doc = SimpleDocTemplate(str(OUT), pagesize=letter, title="Clinical Study Protocol")
    gt = GROUND_TRUTH

    story = [
        Spacer(1, 0.5 * inch),
        Paragraph("CLINICAL STUDY PROTOCOL", styles["Heading2"]),
        Spacer(1, 0.25 * inch),
        Paragraph(gt["studyTitle"], big),
        Spacer(1, 0.4 * inch),
        Paragraph(f"Study Acronym: {gt['studyAcronym']}", lbl),
        Paragraph(f"Sponsor: {gt['sponsorName']}", lbl),
        Paragraph(f"Protocol Number: {gt['protocolIdentifier']}", lbl),
        Paragraph(f"Study Phase: {gt['studyPhase']}", lbl),
        Paragraph(f"Protocol Version: {gt['studyVersionIdentifier']}", lbl),
        PageBreak(),
        Paragraph("1. SYNOPSIS", styles["Heading2"]),
        Paragraph(
            "This is a Phase 2, randomized, double-blind, placebo-controlled, "
            "parallel-group study evaluating ABC-123 in adults with moderate to "
            "severe plaque psoriasis. Approximately 240 participants will be "
            "randomized 1:1:1 to one of three arms: ABC-123 Low Dose, "
            "ABC-123 High Dose, or Placebo.", styles["Normal"]),
    ]
    doc.build(story)

    # Second document: the SoA on a landscape page appended via a fresh build is
    # awkward with SimpleDocTemplate; instead render SoA into the same file by
    # rebuilding with a combined story using a landscape table on its own page.
    _append_soa(str(OUT), gt, styles)
    return OUT


def _append_soa(path: str, gt: dict, styles) -> None:
    """Rebuild the file with the title/synopsis PLUS a SoA table page."""
    big = ParagraphStyle("BigTitle2", parent=styles["Title"], fontSize=20, leading=25)
    lbl = ParagraphStyle("Lbl2", parent=styles["Normal"], fontSize=11, leading=18)
    doc = SimpleDocTemplate(path, pagesize=landscape(letter),
                            title="Clinical Study Protocol")

    header_epoch = ["", *gt["epochs"]]
    header_visit = ["Visit", *gt["visits"]]
    header_time = ["Timing", *gt["timings"]]
    body = []
    for act in gt["activities"]:
        label = act + (" a" if act == gt["footnote_activity"] else "")
        body.append([label] + ["X" if vi in gt["marks"][act] else ""
                               for vi in range(len(gt["visits"]))])
    data = [header_epoch, header_visit, header_time, *body]
    tbl = Table(data, repeatRows=3)
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 2), colors.HexColor("#dbeafe")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("SPAN", (2, 0), (4, 0)),
    ]))

    story = [
        Paragraph("CLINICAL STUDY PROTOCOL", styles["Heading2"]),
        Paragraph(gt["studyTitle"], big),
        Spacer(1, 0.2 * inch),
        Paragraph(f"Study Acronym: {gt['studyAcronym']}", lbl),
        Paragraph(f"Sponsor: {gt['sponsorName']}", lbl),
        Paragraph(f"Protocol Number: {gt['protocolIdentifier']}", lbl),
        Paragraph(f"Study Phase: {gt['studyPhase']}", lbl),
        Paragraph(f"Protocol Version: {gt['studyVersionIdentifier']}", lbl),
        Spacer(1, 0.25 * inch),
        Paragraph("1. SYNOPSIS", styles["Heading3"]),
        Paragraph(
            "This is a Phase 2, randomized, double-blind, placebo-controlled, "
            "parallel-group study evaluating ABC-123 in adults with moderate to "
            "severe plaque psoriasis. Approximately 240 participants will be "
            "randomized 1:1:1 to one of three arms: ABC-123 Low Dose, "
            "ABC-123 High Dose, or Placebo. ABC-123 is administered "
            "subcutaneously every two weeks.", styles["Normal"]),
        Spacer(1, 0.15 * inch),
        Paragraph("2. OBJECTIVES AND ENDPOINTS", styles["Heading3"]),
        Paragraph(f"Primary Objective: {gt['primaryObjective']}", styles["Normal"]),
        Paragraph(f"Primary Endpoint: {gt['primaryEndpoint']}", styles["Normal"]),
        Spacer(1, 0.15 * inch),
        Paragraph("3. ELIGIBILITY CRITERIA", styles["Heading3"]),
        Paragraph("Inclusion Criteria:", styles["Normal"]),
        *[Paragraph(f"{i + 1}. {c}", styles["Normal"])
          for i, c in enumerate(gt["inclusion"])],
        Paragraph("Exclusion Criteria:", styles["Normal"]),
        *[Paragraph(f"{i + 1}. {c}", styles["Normal"])
          for i, c in enumerate(gt["exclusion"])],
        PageBreak(),
        Paragraph("6. SCHEDULE OF ACTIVITIES", styles["Heading2"]),
        Spacer(1, 0.15 * inch),
        tbl,
        Spacer(1, 0.15 * inch),
        Paragraph("a  PK samples are collected only at sites with local "
                  "laboratory capability.", styles["Normal"]),
    ]
    doc.build(story)


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size} bytes)")
    print(f"  arms: {[a['name'] for a in GROUND_TRUTH['arms']]}")
    print(f"  model: {GROUND_TRUTH['interventionModel']} | phase {GROUND_TRUTH['studyPhase']}")
