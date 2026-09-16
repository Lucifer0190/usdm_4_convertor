"""Synthetic protocol page with a real Schedule of Activities TABLE + ground truth.

The table has the features that break naive extractors:
  * a multilevel header (epoch row spanning visits, then visit row, then timing row)
  * X-marked cells (activity performed at that visit)
  * a footnote-gated activity (PK sampling, only at some sites)

Ground truth is machine-checkable so the SoA sub-pipeline can be scored.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path("data/fixtures/protocol_soa.pdf")

# ---- ground truth -------------------------------------------------------- #
EPOCHS = ["Screening", "Treatment", "Treatment", "Treatment", "Follow-up"]
VISITS = ["V1", "V2", "V3", "V4", "V5"]
TIMINGS = ["Day -14", "Day 1", "Week 4", "Week 8", "Week 12"]
ACTIVITIES = ["Informed Consent", "Vital Signs", "ECG", "Blood Chemistry",
              "PK Sample"]
# marks[activity] = list of visit indices (0-based) where an X appears
MARKS: dict[str, list[int]] = {
    "Informed Consent": [0],
    "Vital Signs": [0, 1, 2, 3, 4],
    "ECG": [0, 1, 3],
    "Blood Chemistry": [0, 1, 2, 3, 4],
    "PK Sample": [1, 2],          # footnote-gated
}
FOOTNOTE_ACTIVITY = "PK Sample"
FOOTNOTE_TEXT = ("a  PK samples are collected only at sites with local "
                 "laboratory capability.")


def ground_truth() -> dict:
    return {
        "epochs": EPOCHS, "visits": VISITS, "timings": TIMINGS,
        "activities": ACTIVITIES, "marks": MARKS,
        "footnote_activity": FOOTNOTE_ACTIVITY,
    }


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT), pagesize=landscape(letter),
                            title="Schedule of Activities")

    # Build the table grid (list of rows).
    header_epoch = ["", *EPOCHS]
    header_visit = ["Visit", *VISITS]
    header_time = ["Timing", *TIMINGS]
    body = []
    for act in ACTIVITIES:
        label = act + (" a" if act == FOOTNOTE_ACTIVITY else "")
        row = [label]
        for vi in range(len(VISITS)):
            row.append("X" if vi in MARKS[act] else "")
        body.append(row)
    data = [header_epoch, header_visit, header_time, *body]

    tbl = Table(data, repeatRows=3)
    ts = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 2), colors.HexColor("#dbeafe")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("SPAN", (1, 0), (1, 0)),   # Screening
        ("SPAN", (2, 0), (4, 0)),   # Treatment spans V2-V4
        ("SPAN", (5, 0), (5, 0)),   # Follow-up
    ])
    tbl.setStyle(ts)

    story = [
        Paragraph("6. SCHEDULE OF ACTIVITIES", styles["Heading2"]),
        Spacer(1, 0.2 * inch),
        tbl,
        Spacer(1, 0.2 * inch),
        Paragraph(FOOTNOTE_TEXT, styles["Normal"]),
    ]
    doc.build(story)
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size} bytes)")
    gt = ground_truth()
    print(f"  {len(gt['visits'])} visits, {len(gt['activities'])} activities")
    total = sum(len(v) for v in MARKS.values())
    print(f"  {total} X-marks; footnote-gated activity: {FOOTNOTE_ACTIVITY}")
