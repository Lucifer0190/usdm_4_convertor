# Pipeline & data-flow contracts

> **v0.3 note.** This page describes the ten-layer pipeline (see
> [Architecture](architecture.md)). The implementation is being built in the phases
> described in [`../PLAN.md`](../PLAN.md). As of Phase 1 (CP1-C, 2026-09-24), the
> implemented layers are L0 (ingest), L4 (sharded extraction), L5 (grounding), L6
> (assurance), L7 (assembly), and L8 (validation). L1–L3 and L9 are scheduled for
> Phases 2–5.

Two entry points, both in `usdm4_assure.pipeline`:

- `run(pdf)` — the metadata-only spine (C1). The smallest slice that touches every layer.
- `run_full(pdf)` — the full loop across metadata (C1), design (C2), eligibility (C3),
  objectives (C4), and the Schedule of Activities.

## Current data flow

```
PDF
 │  ingest.pdf.ingest()                         → Document
 ▼
Document ──┬─ extract.metadata.extract_all()     → list[FieldCandidate]
           │      └─ assure.assure()             → list[AssuredField]   (C1)
           ├─ extract.design.extract_design()    → DesignExtract        (C2)
           ├─ extract.eligibility.extract_*()    → EligibilityExtract   (C3)
           ├─ extract.objectives.extract_*()     → ObjectivesExtract    (C4)
           └─ extract.soa.methods (×2)           → SoAGrid, SoAGrid
                  └─ extract.soa.crossval        → AssuredGrid          (SoA)
 ▼
assemble.study.build_full_study(...)             → USDM 4.0 wrapper dict
 │      (data4knowledge Assembler + TimelineAssembler)
 ▼
validate.gate.validate_wrapper(...)              → {structural, d4k, core}
 ▼
data/out_full/study.usdm.json
```

**Phase 1 complete:** as of CP1-C, `assure()` is uniform across C1–C4 (all domains) and SoA,
applying the shared ensemble/grounding/verifier path per [`../DESIGN.md`](../DESIGN.md)
§3 L5–L6. Every field carries a resolved quote (page + character offset + bbox), and a value
with only a failed quote is a hard BLOCK.

## Target data flow (v0.3, in progress)

```
PDF
 │  L0  ingest: PyMuPDF text layer + char bboxes + page images
 ▼
Document
 │  L1  layout + table grids (Docling ∥ MinerU2.5)
 │  L2  multi-page SoA stitching (custom)
 ▼
RoutedDocument
 │  L3  section graph + study fingerprint + prohibited scopes
 ▼
ExtractionPlan
 │  L4  sharded per-domain extraction (<40 fields/call), two-pass emission
 ▼
list[FieldCandidate]  (each carries a verbatim quote, no candidate is ungrounded)
 │  L5  grounding: quote → page/char/bbox, exact-substring hard gate
 ▼
list[GroundedCandidate]
 │  L6  multi-signal confidence → conformal threshold → completeness check → triage
 ▼
list[AssuredField] / AssuredGrid
 │  L7  input sanitizer → usdm4 Assembler → per-section builder fallback
 ▼
USDM 4.0 wrapper
 │  L8  pydantic → d4k rules → CDISC CORE, rule→repair map, bounded repair
 ▼
Validated study + findings
 │  L9  review UI, SME sign-off, Part 11 audit trail
 ▼
Certified study.usdm.json
```

## The shared contracts (current)

Defined in `usdm4_assure.contracts`. These are the vocabulary every layer speaks today;
they extend (not replace) as L5's grounding and L6's conformal/completeness fields land.

### Foundation

- **`Block`** — one positioned text block: `text`, `page`, `bbox`, `kind`
  (`prose | heading | table | footnote`).
- **`Document`** — the deterministic ingest result: `source`, `blocks`, `full_text`,
  `page_images`. `head_text(n)` returns the first *n* pages, where metadata usually lives.

### Extraction → Assurance

- **`FieldCandidate`** — one value for one field from **one** method:
  `field`, `value`, `method`, `source_text`, `source_page`. Under v0.3, `source_text`
  becomes the mandatory verbatim quote that L5 resolves and verifies — a candidate without
  a verifiable quote cannot become an `AssuredField`.
- **`AssuredField`** — a field after Assurance: the chosen `value`, all `candidates`,
  whether methods agreed, the `verifier` verdict, a calibrated `confidence`, and a
  `Decision` (`auto_accept | review | block`). `as_review_row()` renders it for the
  review surface.

### SoA (in `extract/soa/grid.py`)

- **`SoAGrid`** — one method's view of the table: `epochs`, `visits`, `timings`,
  `activities`, `cells` (set of `(activity_i, visit_i)` marks), `footnote_activities`.
- **`AssuredCell`** — a cell after cross-validation: `present`, `provenance`
  (`both | <method>-only | none`), `confidence`, `decision`.
- **`AssuredGrid`** — the reconciled grid: the canonical labels plus a list of
  `AssuredCell`. `present_cells()` and `triage()` summarize it.

## Adding a domain

The architecture's payoff is that a new domain is additive, not a rewrite:

1. Write `extract/<domain>.py` returning `FieldCandidate`s (scalar fields) and/or a small
   structured dataclass (lists like arms/criteria), each candidate carrying a verbatim
   quote from its source.
2. Pass the candidates through `assure.assure()` to get `AssuredField`s — **every** domain
   goes through the shared path; there is no ad-hoc confidence anymore under v0.3.
3. Declare the domain's completeness expectations (§L6) so silent gaps surface as findings.
4. Map the assured output into the `AssemblerInput` in `assemble/study.py`.
5. Re-run `run_full` and check the [conformance](conformance.md) report.

No changes to the Grounding layer, the Assurance layer, the assembler, or the gates are
required.
