# Changelog

All notable changes to USDM4-Assure. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project is pre-release (0.x) and not
yet semantically versioned.

## [Unreleased]

### Added
- **SLM ensemble member** — `--slm` on `convert`/`convert-full` adds a cheap
  different-family small model (default `meta-llama/llama-3.1-8b-instruct`,
  `OPENROUTER_SLM_MODEL` to override) as an independent metadata member. On the reference
  fixture this took metadata from 5/6 to 6/6 auto-accept (SLM independently agreed with
  Claude on the study title). `extract_metadata` generalized to accept multiple LLM
  members; `router.get_slm()` added. *Finding: OpenRouter hosts no clinically fine-tuned
  model — a true clinical SLM needs the fine-tuning path, not an off-the-shelf slug.*
- **OpenRouter as the default LLM gateway** (`llm/openrouter.py`, `llm/config.py`) — one
  key (`OPEN_ROUTER_KEY`, loaded from `.env`), many models, Claude-first and tiered
  (Haiku / Sonnet 4.5 / Opus 4.8, overridable via `OPENROUTER_MODEL_*`). The router now
  resolves OpenRouter → direct Anthropic → stub. Verified live: the Claude ensemble member
  lifted metadata auto-accept from 1/6 to 5/6 on the reference fixture.
- **Deterministic test guard** — `tests/conftest.py` sets `USDM4_NO_LLM=1` so the suite
  never makes live/paid/non-deterministic LLM calls.
- **Documentation set** under `docs/` — architecture, pipeline & contracts, module
  reference, conformance & limitations, development, and references. Google-style
  docstrings on the public API. `CONTRIBUTING.md`, this changelog, and an `mkdocs.yml`.
- **C3 eligibility extractor** (`extract/eligibility.py`) — inclusion/exclusion criteria
  (free text), planned age range, and sex.
- **C4 objectives extractor** (`extract/objectives.py`) — primary/secondary objectives and
  endpoints.
- **Interventions** derived from arms in `assemble/study.py`, wired into the study design.
- **Full loop** (`pipeline.run_full`, `usdm4 convert-full`) — one protocol PDF → one
  USDM 4.0 study across metadata, design, eligibility, objectives, interventions, and SoA.
- **C2 design extractor** (`extract/design.py`) — study type, intervention model, and arms
  parsed from the randomization sentence.
- **SoA sub-pipeline** (`extract/soa/`) — two independent table engines (pdfplumber +
  PyMuPDF), cell-by-cell cross-validation with provenance tags, and assembly into USDM
  ScheduleTimeline entities via the data4knowledge `TimelineAssembler`.
- **Assurance layer** (`assure/`) — multi-method ensemble, grounded verifier, calibrated
  confidence, and per-field triage. Runs without an LLM.
- **Metadata spine** (C1) — `ingest` → `extract/metadata` → `assure` → `assemble` →
  `validate`, with a Claude adapter (`llm/`) that joins as an ensemble member when a key
  is present.
- **Conformance gates** (`validate/gate.py`) — structural (pydantic), d4k rules (offline),
  and CDISC CORE (optional). Docker setup for portability.

### Changed
- Conformance on the reference fixture improved from 24 → 22 d4k findings (14 → 12 failing
  rules) after adding C3/C4 + interventions (`DDF00097`, `DDF00213` cleared).

### Known limitations
- Not yet CORE-clean. A share of residual findings is gated by the upstream
  data4knowledge assembler (objectives not attached to the study design; sponsor role not
  emitted; procedure→intervention references). See `docs/conformance.md`.
- Eligibility is stored as free text (native Boolean-logic modelling is a USDM gap and an
  industry-wide ~30% task).
- Estimands, amendments, the review UI, closed-loop learning, and the Neo4j graph store
  are planned, not built.

## Spike (foundation)
- Proved the backbone: real USDM 4.0 instance loads into the `usdm4` pydantic model; d4k
  and CORE facades reachable; Python 3.12 constraint identified; fork base set to
  data4knowledge. See `spikes/SPIKE_LOG.md`.
