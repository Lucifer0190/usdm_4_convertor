# Pipeline & data-flow contracts

Two entry points, both in `usdm4_assure.pipeline`:

- `run(pdf)` — the metadata-only spine (C1). The smallest slice that touches every layer.
- `run_full(pdf)` — the full loop across metadata (C1), design (C2), eligibility (C3),
  objectives (C4), and the Schedule of Activities.

## Full-loop data flow

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

## The shared contracts

Defined in `usdm4_assure.contracts`. These are the vocabulary every layer speaks.

### Foundation

- **`Block`** — one positioned text block: `text`, `page`, `bbox`, `kind`
  (`prose | heading | table | footnote`).
- **`Document`** — the deterministic ingest result: `source`, `blocks`, `full_text`,
  `page_images`. `head_text(n)` returns the first *n* pages, where metadata usually lives.

### Extraction → Assurance

- **`FieldCandidate`** — one value for one field from **one** method:
  `field`, `value`, `method`, `source_text`, `source_page`. The Assurance layer's whole
  job is to reconcile several of these per field.
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
   structured dataclass (lists like arms/criteria).
2. For scalar fields, pass the candidates through `assure.assure()` to get `AssuredField`s.
3. Map the assured output into the `AssemblerInput` in `assemble/study.py`.
4. Re-run `run_full` and check the [conformance](conformance.md) report.

No changes to the Assurance layer, the assembler, or the gates are required.
