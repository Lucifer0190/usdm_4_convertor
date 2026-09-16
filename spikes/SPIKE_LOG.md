# Spike log — de-risking the fork points (DESIGN.md §9)

Running record of what the spike proved or disproved. Findings feed back into DESIGN.md.

## Environment (probed)
- Python **3.13.5** (Anaconda base), pip 25.1, git 2.44, **Docker 28.3**, Node 20.
- Network egress works for **git + pip** (earlier `curl`/`gh` blanks were unconfigured tools, not a network block).

## Finding 1 — target the `usdm4` package, not `usdm` ✅
- PyPI **`usdm`** (0.67.0, imports as `usdm_model`) = **USDM v3.6.0**. Its bundled examples are v3. Wrong version for us.
- PyPI **`usdm4`** (0.28.0) = **USDM 4.0.0** model. This is our canonical model. (data4knowledge/usdm4)
- Action taken: `pyproject.toml` dependency switched `usdm` → `usdm4`.

## Finding 2 — validation is a solved problem via one facade ★
The `usdm4` package exposes a unified facade that covers **both** Integrity-layer gates from DESIGN.md §3.F:
- `USDM4().validate(path)`      → bundled **d4k rule library** (fast, local) → returns `RulesValidationResults` with `.passed()`, `.count()`, `.finding_count()`, `.outcomes`.
- `USDM4().validate_core(path)` → wraps the **CDISC CORE engine** (`cdisc-rules-engine`) for official conformance.
- `USDM4().prepare_core()`      → pre-populate the CORE cache.
- Ships the **USDM 4.0 JSON schema** (`src/usdm4/core/data/usdm-4-0-schema.json`) and real samples (`validate/samples/sample_usdm_*.json`, `usdmVersion 4.0.0`).
- **Implication:** we do NOT need a separate CORE Docker service for the PoC. The `core` compose service becomes optional. Big simplification.

## Finding 3 — Python 3.13 is not yet supported by the CDISC stack ✅
- `pip install usdm4` on **Python 3.13 FAILS**: transitive dep `cdisc-rules-engine>=0.16.0` pins an older `pydantic-core` with **no cp313 wheel**, so pip tries a Rust source build and fails.
- Fix: **target Python 3.12** (prebuilt wheels, no compiler). Created conda env `usdm4` (py3.12). `pyproject.toml` now pins `requires-python = ">=3.11,<3.13"`. Our Dockerfile already used `python:3.12-slim` — kept.

## Finding 4 — validation backbone RUNS ✅ (proven 2026-08-14)
Ran `spikes/spike_validate.py` in the py3.12 env against the real CDISC sample
`sample_usdm_4.json` (study **ALXN1840-WD-204** — an actual Alexion Wilson-Disease protocol; usable bootstrap ground truth).

1. **Pydantic structural load: SUCCEEDED.** `Wrapper.model_validate(raw)` loaded the full v4.0.0 instance; read `study.name`, `studyVersions[0]`, 1 studyDesign. → The canonical-model approach (DESIGN.md §2) is proven.
2. **d4k rule validation: RUNS OFFLINE.** 213 rules executed, `passed=False`, **42 findings** (e.g. DDF00006/DDF00010/DDF00035). Usable immediately as our fast local gate — no network/key needed.
3. **CDISC CORE: reachable but gated on an API key.** `validate_core()` downloaded jsonata resources, then warned: *"CDISC Library API key not available"* → could not fetch the full rule + CT data, returned 0 findings. **CORE requires `CDISC_LIBRARY_API_KEY`** (free CDISC account).

### Two real dependencies this surfaced
- ⚠️ **`CDISC_LIBRARY_API_KEY`** needed for the official CORE gate + controlled-terminology download. Free to register at CDISC Library; this is an access item to action now (it also unblocks the `coding/` layer's CT lookups).
- 📌 **"Conformant" is nuanced:** even CDISC's *own* sample fails **18 rules / 42 findings** — and they are *genuine* rules, not noise. Sampled rule texts:
  - `DDF00006` Timing windows must be fully defined
  - `DDF00010` names of all child instances must be unique
  - `DDF00185` if a dose is specified, a corresponding unit must be present
  - `DDF00188` planned sex must include a valid value
  - `DDF00181` date values associated to a study protocol …
  - `DDF00164/165` section number/title display (narrative/M11-layer — likely out of scope for extraction)
  So our "≥90% pass" target must be pinned to a **specific rule set + USDM/CT version**, and rules split into *extraction-relevant* vs *narrative/display*. Reaching **exactly 0 findings is not the bar** — matching-or-beating the reference sample's conformance on the extraction-relevant subset is.

### Tooling notes
- `conda run -n usdm4 python <file>` works; `conda run ... python -c "multiline"` does NOT (conda rejects newline args) — always use a file.
- d4k `RulesValidationResults`: `.passed()`, `.count()` (rules run), `.finding_count()`, `.outcomes{rule: RuleOutcome}`; `RuleOutcome.errors` is a `simple_error_log.errors.Errors` (use `str()`/`.dump()`, not indexing).

## Finding 5 — fork base pivots: Protocol2USDM is gone, data4knowledge is richer ✅
- **`Panikos/Protocol2USDM` returns "Repository not found"** (private or removed) under every casing. Cannot fork it. (The earlier web description was accurate at the time; the repo is no longer public.)
- But **`data4knowledge/usdm4` ships far more than a model** — submodules: `api, assembler, builder, convert, bc, ct, expander, core, rules, data_store, minimum, utility`.
  - `assembler` / `builder` → construct USDM from structured inputs (our assemble layer, partly done).
  - `bc` / `ct` → **BiomedicalConcept + controlled-terminology** helpers (our coding layer foundations).
  - `convert` → format conversion; `expander` → reference expansion.
- **Decision:** extraction/assembly/coding base = **data4knowledge** (usdm4 + study_definitions_workbench), not Protocol2USDM. Same org owns model + CORE + these helpers → tighter integration. The moat (Assurance + Learning) is unchanged and still entirely ours to build.

## SPINE RUNS END-TO-END ✅ (2026-08-14) — Foundation → Extraction → Assurance → Integrity
Vertical slice on the metadata (C1) domain, proven on a synthetic fixture with known ground truth
(`spikes/make_fixture.py` → study "ASCEND-2", sponsor Northwind, phase 2, id NWT-ABC123-201, v2.0).

Command: `usdm4 convert data/fixtures/protocol_ABC123.pdf`  → `data/out/{study.usdm.json, review.json}`
- **Extraction: 6/6 metadata values correct** vs ground truth (no LLM — two deterministic methods).
- **Assurance working as designed:** `studyPhase` had **2 independent methods agree → auto_accept @ conf 1.00**; single-source fields correctly routed to **review** (not falsely trusted); `protocolIdentifier` showed the ensemble catching a real cross-method **disagreement**. Triage: 1 auto_accept / 5 review / 0 block.
- **Gates:** structural **PASS** · d4k **213 rules / 10 findings** (minimal skeleton) · CORE skipped (no key).
- **Tests: 4/4 pass** (`tests/test_spine.py`) — values correct, phase auto-accepts, structural passes, d4k runs.
- **LLM is a drop-in 3rd ensemble member**: no `ANTHROPIC_API_KEY` → runs the 2 deterministic paths; set the key → Claude (tiered: Sonnet extract / Opus verify) joins automatically, lifting agreement→more auto-accept. No other code changes.

### Two small template gotchas fixed
- `minimum_template.json` ships `study.id = "FAKE-UUID"` → assemble must mint a real UUID.
- d4k `RulesValidationResults.count/passed/finding_count` are **properties, not methods** → read defensively.

## SoA SUB-PIPELINE BUILT & PROVEN ✅ (2026-08-14) — the hardest module
Vision-first pattern realized WITHOUT a key using two independent deterministic table extractors.

Fixture `spikes/make_soa_fixture.py` → landscape SoA table: multilevel header (epoch-span / visit / timing),
5 activities × 5 visits, 16 X-marks, a footnote-gated activity (PK Sample). Known ground truth.

Pipeline: `PDF → extract_pdfplumber + extract_pymupdf (independent) → cross_validate → build_soa (TimelineAssembler)`.
- **Extraction + cross-validation: 16/16 cells correct** (0 missed, 0 extra); both methods agreed → all auto_accept; epochs forward-filled (Screening/Treatment×3/Follow-up); footnote activity detected.
- **Assembly into USDM: 0 assembler errors** → 3 epochs (dedup), 5 encounters, 5 activities, **5 ScheduledActivityInstances** (one per visit, each with the correct activityIds), 1 Condition (footnote), 5 Timings.
- **Per-visit SAI activity sets match ground truth exactly** for all 5 visits.
- **Tests: `tests/test_soa.py` 6/6 pass; full suite 10/10.**
- CLI: `usdm4 convert-soa <pdf>`.

### Key design facts learned
- **SAI is per-encounter, not per-cell**: one ScheduledActivityInstance per visit whose `activityIds[]` = the X-marked rows in that column. Elegant mapping from a grid.
- **`data4knowledge.TimelineAssembler`** (`usdm4.assembler`) mints conformant Encounter/Epoch/Activity/SAI/Timing/Condition from a structured `TimelineInput` (schema in `assembler/schema/timeline_schema.py`) — **offline, using the bundled CT cache** (no CDISC key). This is our SoA assemble engine; we only build the input dict from the AssuredGrid.
- Wrapping SoA in a full StudyDesign (arms/epochs/cells/population) is deferred to the **C2 design-skeleton domain (task A, next)** — a principled scope line, not a gap.
- Two independent extractors agreeing on a clean synthetic table → all auto_accept (honest). Real messy protocols diverge more → that's where the review triage pays off; the mechanism is proven either way.

## FULL LOOP CLOSED ✅ (2026-08-14) — one PDF → one complete USDM 4.0 study
C2 design-skeleton domain added and everything composed via the top-level `data4knowledge.Assembler`.

Fixture `spikes/make_full_fixture.py` = title page + synopsis (3 arms, parallel) + SoA table, one PDF.
Pipeline `usdm4 convert-full <pdf>` → `run_full`: ingest → C1 metadata(assured) → C2 design → SoA(crossval) → `build_full_study`.
- **C2 design extractor** (`extract/design.py`): parses study type, intervention model, and **arms from the randomization sentence** ("randomized 1:1:1 to … ABC-123 Low Dose, ABC-123 High Dose, or Placebo" → 3 arms with types Experimental/Experimental/Placebo Comparator). Anchor on `arms:`/ratio cue (not the first "to") — fixed a mis-parse.
- **Full assemble** (`assemble/study.py`): builds a `data4knowledge` **AssemblerInput** (identification/document/population/study_design/study/**soa**=our TimelineInput) → `Assembler.execute` → `.wrapper()` → complete Study.
- **Result: 0 assembler errors**, structural **PASS**, arms=3, epochs=3, encounters=5, activities=5, SAIs=5, **phase resolved to CDISC C15601 "Phase II Trial"**. d4k 213 rules / 24 findings (expected — no objectives/endpoints/eligibility yet).
- **Tests: `tests/test_full.py` 5/5; full suite 15/15.**

### Facts learned
- Top-level `Assembler` (`usdm4.assembler.assembler`): `Assembler(root, Errors()).execute(AssemblerInput_dict)` then `.wrapper(name, version)`. Its **`soa` field takes our TimelineInput directly** — SoA plugs straight in.
- `study_design.arms` (≥1) fills the CORE-000938 gap the minimum assembler leaves (arms/studyCells empty).
- encoder resolves human strings: arm types "Experimental"/"Placebo Comparator"/"Active Comparator"; intervention_model "Parallel"/…; phase "Phase 2"→C15601. Bundled CT → offline, no key.
- `wrapper.model_dump()` leaves UUID objects → serialize with `json.dumps(..., default=str)`.
- **What's still needed for full CORE conformance** (the 24 findings): objectives/endpoints/estimands, eligibility criteria, timing windows, planned enrollment/duration — the next domains (C3/C4).

## CONFORMANCE PASS: C3 eligibility + C4 objectives + interventions (2026-08-14)
Added domains to drive d4k findings down. Extractors: `extract/eligibility.py` (inclusion/exclusion
lists via region + numbered-split; age range; sex), `extract/objectives.py` (primary/secondary
objective+endpoint by label). Interventions derived from arms. All wired into the AssemblerInput
(`population.demographics`, `population.inclusion_exclusion`, `study_design.interventions`, `objectives`).

Result on the full fixture (now includes Objectives + Eligibility sections):
- **d4k findings 24 → 22; failing rules 14 → 12.** Cleared **DDF00097** (planned age range) and **DDF00213** (interventions for parallel design). Study now carries real 6 eligibility criteria, age 18–75, 1 primary objective+endpoint, 3 interventions.
- Tests: `tests/test_full.py` 8/8 (added eligibility/objectives/demographics assertions); full suite 18/18.

### ‼️ KEY FINDING — full CORE conformance is gated partly by the UPSTREAM assembler, not our extractors
The residual 12 rules split into three buckets:
1. **Known data4knowledge assembler gaps** (cannot clear via input; confirmed by their own `tests/.../integration/test_assembler_to_core.py` docstring which pins known-failing rules): objectives/endpoints NOT attached to studyDesign despite valid input (`studyDesign.objectives == 0`) → **DDF00084, DDF00041**; sponsor StudyRole/identifier not emitted → **DDF00172, DDF00201**; procedure→intervention reference → **DDF00101**.
2. **Domains needing richer data we don't extract yet**: SoA timing windows/anchors → DDF00006/00025/00031; BiomedicalConcept ids on activities → DDF00075; main-timeline planned duration → DDF00153.
3. **Structural linked-list** ordering → DDF00087/00088.
**Implication for the plan:** reaching CORE-clean output requires either (a) contributing fixes upstream to data4knowledge's assembler (objectives/sponsor/procedure), or (b) constructing those USDM parts ourselves via the lower-level `builder` (bypassing the assembler) — a larger effort to budget. Our extraction layer is not the blocker. This is exactly the kind of maturity risk a PoC exists to surface.

## Running implications for DESIGN.md
- §2 fork base confirmed usable; add **`usdm4` (data4knowledge)** as the model+validation dependency explicitly.
- §3.F: CORE reachable in-process via `validate_core()`; the standalone CORE container is optional, not required.
- New global constraint: **Python 3.12** until the CDISC stack ships 3.13 wheels.
