"""Integrity E — assemble assured metadata into a conformant USDM 4.0 skeleton.

Strategy for the spine: start from the package's minimal *conformant* USDM 4.0
skeleton and patch in the assured field values, then hand off to validation.
Fields with no home in the minimal skeleton yet (phase, acronym — they live under
StudyDesign / a second title, later domains) are carried in the review output but
not injected, which is stated honestly rather than faked.
"""
from __future__ import annotations

import copy
import json
import uuid
from importlib import resources

from usdm4_assure.contracts import AssuredField

# Where each assured field is written in the USDM tree.
_TEMPLATE = "minimum_template.json"


def _load_template() -> dict:
    with resources.files("usdm4_assure.assemble").joinpath(_TEMPLATE).open(
            "r", encoding="utf-8") as fh:
        return json.load(fh)


def assemble_metadata(assured: list[AssuredField]) -> dict:
    """Return a USDM 4.0 wrapper dict with assured metadata patched in."""
    vals = {a.field: a.value for a in assured if a.value}
    doc = copy.deepcopy(_load_template())
    # The template ships a "FAKE-UUID" placeholder for study.id — mint a real one.
    doc["study"]["id"] = str(uuid.uuid4())
    sv = doc["study"]["versions"][0]

    if title := vals.get("studyTitle"):
        sv["titles"][0]["text"] = title
        doc["study"]["description"] = title
        doc["study"]["label"] = title[:120]
        doc["study"]["name"] = (vals.get("studyAcronym") or title[:40]).strip()
    if ident := vals.get("protocolIdentifier"):
        sv["studyIdentifiers"][0]["text"] = ident
    if sponsor := vals.get("sponsorName"):
        sv["organizations"][0]["name"] = sponsor
    if ver := vals.get("studyVersionIdentifier"):
        # keep it numeric-ish; USDM versionIdentifier is a free string
        sv["versionIdentifier"] = ver

    doc["systemName"] = "USDM4-Assure"
    doc["systemVersion"] = "0.1.0"
    return doc
