"""``corrections.json`` sidecar for mechanical re-derivation disagreements (task 2.6).

A disagreement between what extraction claimed and what
:func:`soa.rederive.rederive_grid` mechanically found is recorded here, keyed
by the source PDF, for a reviewer to resolve. The raw ``StitchedGrid``/
``SoAGrid`` is never mutated in place — this sidecar is the only place a
correction is written, and it is additive: each write appends the run's
disagreements under that PDF's key, it never edits or drops an existing entry.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from usdm4_assure.soa.rederive import MarkComparison, disagreements


def write_corrections(path: str | Path, pdf_path: str | Path,
                      comparisons: list[MarkComparison]) -> Path:
    """Append this run's disagreements to ``path`` under ``pdf_path``'s key.

    Returns ``path``. A PDF with no disagreements still gets an (empty) entry,
    so "we checked and found nothing" stays distinguishable from "we never checked".
    """
    path = Path(path)
    data = json.loads(path.read_text()) if path.exists() else {}
    key = str(Path(pdf_path))
    data[key] = [asdict(c) for c in disagreements(comparisons)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return path


def read_corrections(path: str | Path, pdf_path: str | Path) -> list[dict]:
    """The recorded disagreements for ``pdf_path``, or ``[]`` if none were ever written."""
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get(str(Path(pdf_path)), [])
