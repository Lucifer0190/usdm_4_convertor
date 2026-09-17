"""SoA sub-pipeline test: PDF table -> 2 independent extractors -> cross-validation
-> USDM ScheduleTimeline entities, all checked against known ground truth.

Proves the hardest, most safety-critical module: the Schedule of Activities.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_soa_fixture import build, ground_truth

from usdm4_assure.assemble.soa import build_soa
from usdm4_assure.extract.soa.crossval import cross_validate
from usdm4_assure.extract.soa.methods import (
    extract_pdfplumber,
    extract_pymupdf,
)


@pytest.fixture(scope="module")
def graded():
    pdf = build()
    gt = ground_truth()
    ag = cross_validate([extract_pdfplumber(pdf), extract_pymupdf(pdf)])
    return ag, gt


def test_grid_dimensions_match(graded):
    ag, gt = graded
    assert ag.visits == gt["visits"]
    assert ag.activities == gt["activities"]
    assert ag.epochs == gt["epochs"]


def test_all_cells_correct(graded):
    ag, gt = graded
    got = {(ag.activities[c.activity_i], c.visit_i) for c in ag.present_cells()}
    expected = {(a, vi) for a, marks in gt["marks"].items() for vi in marks}
    assert got == expected, f"missed={expected - got} extra={got - expected}"


def test_two_methods_agree_auto_accept(graded):
    ag, _ = graded
    assert ag.methods == ["pdfplumber", "pymupdf"]
    # every present cell seen by both independent methods -> auto_accept
    assert all(c.decision == "auto_accept" for c in ag.present_cells())


def test_footnote_gated_activity_detected(graded):
    ag, gt = graded
    assert gt["footnote_activity"] in ag.footnote_activities


def test_assembles_to_usdm_scheduletimeline(graded):
    ag, gt = graded
    res = build_soa(ag)
    assert res["assembler_errors"] == []
    s = res["summary"]
    assert s["encounters"] == len(gt["visits"])
    assert s["scheduled_instances"] == len(gt["visits"])
    assert s["conditions"] >= 1          # footnote -> Condition
    assert s["timings"] == len(gt["visits"])


def test_sai_activities_match_ground_truth(graded):
    ag, gt = graded
    res = build_soa(ag)
    by_enc = res["sai_activities_by_encounter"]
    # map each encounter (by timing label) to its expected activity set
    for vi, timing in enumerate(gt["timings"]):
        expected = {a for a, marks in gt["marks"].items() if vi in marks}
        # find the encounter whose activity set matches; assert one does
        assert any(set(acts) == expected for acts in by_enc.values()), (
            f"no SAI matches visit {gt['visits'][vi]} expected {expected}")
