# Module reference

The package lives under `src/usdm4_assure/`. Planned modules are stubbed with a
role docstring so the layer map is visible in the tree.

## Foundation

| Module | Role |
|---|---|
| `ingest/pdf.py` | `ingest()` — PDF → `Document` (positioned blocks + rendered page images) via PyMuPDF. Deterministic, no LLM. |
| `retrieve/` | *(planned)* section index, header-preserving RAG chunking, retrieval routing. |

## Extraction

| Module | Role |
|---|---|
| `extract/metadata.py` | **C1** — study title, acronym, sponsor, phase, identifiers, version. Two independent deterministic methods (`labels`, `titlepage`) plus an optional `claude` member. |
| `extract/design.py` | **C2** — study type, intervention model, and arms (parsed from the randomization sentence), with arm types. |
| `extract/eligibility.py` | **C3** — inclusion/exclusion criteria (stored as free text per USDM), planned age range, sex. |
| `extract/objectives.py` | **C4** — primary/secondary objectives and endpoints (Estimands deferred). |
| `extract/soa/methods.py` | Two independent SoA table extractors (`pdfplumber`, `pymupdf`) plus a drop-in `vision` member. |
| `extract/soa/crossval.py` | Cell-by-cell cross-validation → `AssuredGrid` with provenance tags. |
| `extract/soa/grid.py` | The SoA intermediate representation (`SoAGrid`, `AssuredCell`, `AssuredGrid`). |

## Assurance ★

| Module | Role |
|---|---|
| `assure/__init__.py` | The moat. `assure()` groups candidates per field (ensemble), `verify()` grounds each value against its source span, and confidence + `Decision` are computed and calibrated. Runs fully without an LLM. |

## Integrity

| Module | Role |
|---|---|
| `assemble/metadata.py` | Patch assured metadata into a minimal conformant USDM skeleton (used by the C1 spine). |
| `assemble/soa.py` | `AssuredGrid` → `TimelineInput` → USDM ScheduleTimeline entities via the data4knowledge `TimelineAssembler`. |
| `assemble/study.py` | Compose the full `AssemblerInput` from every domain and run the top-level `Assembler` → one USDM 4.0 study. |
| `validate/gate.py` | The conformance gates: pydantic structural, d4k rule engine (offline), CDISC CORE (optional, needs API key). |
| `coding/` | *(planned)* NCI EVS / CDISC Library coded-value lookup with caching. |

## Model orchestration

| Module | Role |
|---|---|
| `llm/base.py` | The `LLM` protocol and tiered model routing (`ModelTier`, `tier_for`). |
| `llm/claude.py` | Claude adapter — pinned model ids per tier, extended-thinking budgets; activates when `ANTHROPIC_API_KEY` is set. |
| `llm/router.py` | `get_llm()` returns Claude when a key is present, otherwise a no-op `StubLLM`. |

## Certification, Learning, Data (planned)

| Module | Role |
|---|---|
| `review/` | Provenance review UI surface; SME sign-off; audit trail. |
| `learn/` | Capture corrections → few-shot bank → SLM training datasets. |
| `graph/` | Neo4j property-graph loader for downstream SDTM automation. |

## Orchestration & CLI

| Module | Role |
|---|---|
| `pipeline.py` | `run()` (metadata spine) and `run_full()` (full loop). |
| `cli.py` | `usdm4 convert`, `convert-soa`, `convert-full`, `version`. |
| `contracts.py` | Shared dataclasses spoken between layers. |
