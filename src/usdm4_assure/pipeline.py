"""Pipeline orchestration — wires the layers into runnable end-to-end flows.

Two entry points:

* :func:`run` — the metadata-only spine (C1). The smallest slice that exercises
  every layer: Foundation(ingest) -> Extraction -> Assurance -> Integrity.
* :func:`run_full` — the full loop: metadata (C1) + design (C2) + eligibility (C3)
  + objectives (C4) + Schedule of Activities, assembled into one USDM 4.0 study.

Both share the same pattern, which is the point of the architecture: adding a
domain is another extractor feeding the same Assurance + assemble path, not a
rewrite. See ``docs/pipeline.md`` for the data-flow contracts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from usdm4_assure.assemble.metadata import assemble_metadata
from usdm4_assure.assure import assure
from usdm4_assure.contracts import AssuredField, Decision
from usdm4_assure.extract import metadata as c1
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.llm.router import get_llm
from usdm4_assure.validate.gate import validate_wrapper


@dataclass
class FullResult:
    """Everything the full pipeline produced for one protocol.

    Attributes:
        assured_meta: Metadata (C1) fields after the Assurance layer.
        design: The ``DesignExtract`` (C2) — study type, model, arms.
        grid: The ``AssuredGrid`` — the cross-validated Schedule of Activities.
        study: The ``build_full_study`` output dict (wrapper, validation, summary).
        out_dir: Directory the artifacts were written to.
        eligibility: The ``EligibilityExtract`` (C3), or ``None``.
        objectives: The ``ObjectivesExtract`` (C4), or ``None``.
    """
    assured_meta: list[AssuredField]
    design: object
    grid: object
    study: dict
    out_dir: Path
    eligibility: object = None
    objectives: object = None


def run_full(pdf_path: str | Path, out_dir: str | Path = "data/out_full",
             run_core: bool = False, use_slm: bool = False) -> FullResult:
    """Run the full loop: PDF -> C1 metadata + C2 design + C3/C4 + SoA -> one study.

    Ingests the PDF once, runs every domain extractor over it, reconciles the SoA
    with two independent table methods, then assembles a single conformant USDM 4.0
    study via the data4knowledge assembler and validates it. Writes
    ``study.usdm.json`` to ``out_dir`` when assembly succeeds.

    Args:
        pdf_path: Path to the source protocol PDF.
        out_dir: Directory for artifacts (rendered pages + assembled study JSON).
        run_core: If ``True``, also run the official CDISC CORE gate (requires
            ``CDISC_LIBRARY_API_KEY``); otherwise only the offline d4k gate runs.

    Returns:
        A ``FullResult`` bundling every domain's extract, the assembled study,
        its validation report, and the output directory.
    """
    from usdm4_assure.assemble.study import build_full_study
    from usdm4_assure.extract.design import extract_design
    from usdm4_assure.extract.eligibility import extract_eligibility
    from usdm4_assure.extract.objectives import extract_objectives
    from usdm4_assure.extract.soa.crossval import cross_validate
    from usdm4_assure.extract.soa.methods import extract_pdfplumber, extract_pymupdf

    pdf_path, out_dir = Path(pdf_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = ingest(pdf_path, image_dir=out_dir / "pages")
    members = _members(use_slm)

    assured_meta = assure(c1.extract_all(doc, members), doc, c1.FIELDS)
    meta = {a.field: a.value for a in assured_meta if a.value}
    _, design = extract_design(doc, meta, members[0])
    elig = extract_eligibility(doc)
    objs = extract_objectives(doc)
    grid = cross_validate([extract_pdfplumber(pdf_path), extract_pymupdf(pdf_path)])

    study = build_full_study(assured_meta, design, grid, elig, objs, run_core=run_core)
    if study.get("wrapper"):
        (out_dir / "study.usdm.json").write_text(
            json.dumps(study["wrapper"], indent=2, default=str), encoding="utf-8")
    return FullResult(assured_meta, design, grid, study, out_dir, elig, objs)


@dataclass
class PipelineResult:
    """Result of the metadata-only spine (:func:`run`).

    Attributes:
        assured: The metadata fields after the Assurance layer.
        wrapper: The assembled (partial) USDM 4.0 wrapper dict.
        validation: The conformance-gate report (structural + d4k + core).
        llm_name: Which LLM member ran (``"claude"`` or ``"stub"``).
        out_dir: Directory the artifacts were written to.
    """
    assured: list[AssuredField]
    wrapper: dict
    validation: dict
    llm_name: str
    out_dir: Path

    @property
    def review_stats(self) -> dict:
        """Count of fields per triage decision (auto_accept / review / block)."""
        c = {d.value: 0 for d in Decision}
        for a in self.assured:
            c[a.decision.value] += 1
        return c


def _members(use_slm: bool) -> list:
    """The LLM ensemble members: the primary (Claude) plus an optional SLM.

    Claude-only by default (cost control); ``use_slm`` adds a cheap different-family
    SLM member, which strengthens the cross-family agreement signal.
    """
    from usdm4_assure.llm.router import get_slm
    members = [get_llm()]
    if use_slm:
        members.append(get_slm())
    return members


def run(pdf_path: str | Path, out_dir: str | Path = "data/out",
        run_core: bool = False, use_slm: bool = False) -> PipelineResult:
    """Run the metadata-only spine (C1) end-to-end and write artifacts.

    The smallest demonstration of the architecture: ingest -> extract metadata
    -> Assurance -> assemble a partial study -> validate. Writes
    ``study.usdm.json`` and ``review.json`` (provenance + per-field triage).

    Args:
        pdf_path: Path to the source protocol PDF.
        out_dir: Directory for the output artifacts.
        run_core: If ``True``, additionally run the CDISC CORE gate.
        use_slm: If ``True``, add a cheap SLM member (different family than Claude)
            to the ensemble. Off by default for cost control.

    Returns:
        A ``PipelineResult`` with the assured fields, assembled wrapper, and
        validation report.
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Foundation
    doc = ingest(pdf_path, image_dir=out_dir / "pages")

    # Extraction (C1) + LLM member(s) if a key is present
    members = _members(use_slm)
    llm = members[0]
    candidates = c1.extract_all(doc, members)

    # Assurance ★
    assured = assure(candidates, doc, c1.FIELDS)

    # Integrity: assemble -> validate
    wrapper = assemble_metadata(assured)
    validation = validate_wrapper(wrapper, run_core=run_core)

    # Emit artifacts
    (out_dir / "study.usdm.json").write_text(
        json.dumps(wrapper, indent=2), encoding="utf-8")
    review = {
        "source": str(pdf_path),
        "llm": llm.name,
        "decision_summary": {d.value: 0 for d in Decision},
        "fields": [a.as_review_row() for a in assured],
        "validation": validation,
    }
    for a in assured:
        review["decision_summary"][a.decision.value] += 1
    (out_dir / "review.json").write_text(
        json.dumps(review, indent=2), encoding="utf-8")

    return PipelineResult(assured, wrapper, validation, llm.name, out_dir)
