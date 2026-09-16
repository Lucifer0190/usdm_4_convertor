"""Integrity E (SoA) — assured grid -> valid USDM ScheduleTimeline entities.

Uses the data4knowledge `TimelineAssembler`, which mints conformant Encounter /
StudyEpoch / Activity / ScheduledActivityInstance / Timing / Condition objects
(with proper cross-references and CDISC Codes from the bundled CT cache — no API
key needed) from a structured SoA description.

We build that structured description from our AssuredGrid, so the pipeline is:
    PDF -> extract (2 methods) -> cross-validate -> THIS -> USDM SoA entities.

Wrapping these in a full StudyDesign (arms / population / cells) belongs to the
design-skeleton domain (C2) and is intentionally out of scope here.
"""
from __future__ import annotations

import os
import re

from usdm4_assure.extract.soa.grid import AssuredGrid

_TIME_RE = re.compile(r"(day|week|month)\s*(-?\d+)", re.IGNORECASE)
_UNIT = {"day": "days", "week": "weeks", "month": "months"}


def _parse_timepoint(text: str, index: int) -> dict:
    m = _TIME_RE.search(text or "")
    if m:
        unit = _UNIT[m.group(1).lower()]
        value = m.group(2)
    else:
        unit, value = "days", str(index)
    return {"index": str(index), "text": text or f"T{index}",
            "value": value, "unit": unit}


def grid_to_timeline_input(ag: AssuredGrid) -> dict:
    """Map an :class:`AssuredGrid` to the ``TimelineAssembler`` input schema.

    Footnote-gated activities are given letter markers (``a``, ``b`` …) and a
    matching ``ConditionItem`` so the assembler emits USDM ``Condition`` objects.

    Args:
        ag: The cross-validated Schedule of Activities grid.

    Returns:
        A ``TimelineInput``-shaped dict (``epochs``/``visits``/``timepoints``/
        ``activities``/``conditions`` blocks) ready for the assembler.
    """
    # footnote marker per gated activity: assign 'a', 'b', ...
    gated = list(ag.footnote_activities)
    marker = {name: chr(ord("a") + i) for i, name in enumerate(gated)}

    epochs = {"found": True, "items": [{"text": e} for e in ag.epochs]}
    visits = {"found": True,
              "items": [{"text": v, "references": []} for v in ag.visits]}
    timepoints = {"found": True,
                  "items": [_parse_timepoint(t, i) for i, t in enumerate(ag.timings)]}

    # activities: for each row, the visit indices where a present cell exists
    present_by_act: dict[int, list[int]] = {}
    for c in ag.present_cells():
        present_by_act.setdefault(c.activity_i, []).append(c.visit_i)

    activity_items = []
    conditions = []
    for ai, name in enumerate(ag.activities):
        refs = [marker[name]] if name in marker else []
        vis = [{"index": vi, "references": refs}
               for vi in sorted(present_by_act.get(ai, []))]
        activity_items.append({"name": name, "visits": vis, "references": refs})
        if name in marker:
            conditions.append({"reference": marker[name],
                               "text": f"{name} is footnote-gated ({marker[name]})."})

    return {
        "table_type": "main_soa",
        "epochs": epochs,
        "visits": visits,
        "timepoints": timepoints,
        "windows": {"found": False, "items": []},
        "activities": {"found": True, "items": activity_items},
        "conditions": {"found": bool(conditions), "items": conditions},
    }


def build_soa(ag: AssuredGrid) -> dict:
    """Run the TimelineAssembler; return the assembled USDM SoA entities + summary."""
    import usdm4
    from simple_error_log.errors import Errors
    from usdm4.assembler.timeline_assembler import TimelineAssembler
    from usdm4.builder.builder import Builder

    root = os.path.dirname(usdm4.__file__)
    builder = Builder(root, Errors())
    errors = Errors()
    ta = TimelineAssembler(builder, errors)
    ta.execute(grid_to_timeline_input(ag))

    timelines = ta.timelines
    sais = timelines[0].instances if timelines else []
    encounters = ta.encounters
    activities = ta.activities

    # SAI per encounter -> activityIds. Verify by mapping ids back to names.
    act_name = {a.id: (getattr(a, "label", None) or a.name) for a in activities}
    enc_name = {e.id: (e.label or e.name) for e in encounters}
    sai_map = {}
    for sai in sais:
        enc = enc_name.get(getattr(sai, "encounterId", None), getattr(sai, "name", "?"))
        sai_map[enc] = [act_name.get(i, i) for i in getattr(sai, "activityIds", [])]

    return {
        "entities": {
            "epochs": ta.epochs, "encounters": encounters,
            "activities": activities, "timelines": timelines,
            "conditions": ta.conditions,
        },
        "summary": {
            "epochs": len(ta.epochs), "encounters": len(encounters),
            "activities": len(activities),
            "scheduled_instances": len(sais),
            "conditions": len(ta.conditions),
            "timings": len(timelines[0].timings) if timelines else 0,
        },
        "sai_activities_by_encounter": sai_map,
        "assembler_errors": [str(e) for e in errors.errors] if hasattr(errors, "errors") else [],
    }
