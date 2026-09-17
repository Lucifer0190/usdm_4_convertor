# Changelog

All notable changes to USDM4-Assure. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project is pre-release (0.x) and not
yet semantically versioned.

## [Unreleased]

### Architecture (v0.3.1) — Frontier-only model strategy, verified live

**Major change:** v0.3 proposed SLM-tiered extraction (cheap small models like Llama-3.1-8B
and gpt-oss-20b for specific roles to cut cost). Re-analyzed the published evidence in
`PLAN.md` §4.2 and found that **frontier models outperform small models in every measured
domain**. Updated the strategy to accuracy-first: frontier LLMs are the default for all
roles, and SLMs are used only when empirically proven to beat frontier on that task. One
specialist survives this test: **MinerU2.5 beats Gemini-2.5-Pro on table structure (88.2 vs
85.7 TEDS).**

The following changes reflect this:
- Removed SLM ensemble member (Llama-3.1-8B) from the extraction path — cross-family
  verification now uses `openai/gpt-5.1` (different family, frontier accuracy).
- Removed cheap small-model routing (gpt-oss-20b for section classification) — deterministic
  signals (bookmarks, ToC, headings) now handle most routing; residue goes to frontier LLM.
- Removed `qwen3-vl-30b-a3b-instruct` SoA cell first-pass — frontier VLM now handles all
  cell extraction with cross-family checks.
- Documented cost control via disk cache (re-runs free after first pass) and verification
  on the uncertain subset only, not via model downgrade.
- Updated `PLAN.md` §4, `DESIGN.md` §4, `architecture.html` model tables, `docs/development.md`
  to reflect frontier-only roles in `config/models.yaml`.

Earlier verification (live catalog):
- Queried the live catalog (`GET /api/v1/models`, 444 models, 2026-09-17) and confirmed
  OpenRouter proxies only chat-completion APIs, not task-specific NER/NLI encoders or
  caller-uploaded fine-tuned checkpoints. `GLiNER-BioMed` and `MiniCheck-FT5` are
  **self-hosted**, not OpenRouter-served — a deliberate infrastructure decision.
- Verified frontier tier slugs against catalog: `anthropic/claude-sonnet-4.5`,
  `openai/gpt-5.1`, `google/gemini-3.1-pro-preview` (three families for cross-family
  verification).
- Confirmed logprobs support gap: `llama-3.1-8b-instruct` lists `logprobs`/`top_logprobs`;
  `claude-sonnet-4.5` does not.

### Architecture (v0.3)
- **Rewrote `DESIGN.md` and `docs/` against a published-literature review** (`PLAN.md`,
  new). Two v0.2 claims did not survive the review and are retracted rather than carried
  forward:
  - The "~89% field / ~76% SoA market ceiling" was not a matched benchmark. The 89%
    figure is a vendor-authored (Banting Health AI) n=23 study on a bespoke non-USDM
    schema with a partly-LLM-generated gold standard; the 76% figure (Kramer/MITRE
    ProtocolMiner, peer-reviewed, genuinely USDM-targeted) is a whole-table pass rate
    (22/29 protocols), not a field-level metric. Quoting them together implied a
    benchmark that does not exist.
  - "Two independent paths at ~89% each agree on ~80-85% of fields, raising precision to
    ~97-99% on the agreed set" assumed near-independent errors. Measured cross-model
    error correlation is 0.74-0.82 (GPT-4o/Claude 0.822), and 48% of mistakes replicate
    across model families. Ensemble agreement is retained as one input to a calibrated
    confidence model, not a precision guarantee.
- New architecture layers added to the design (not yet all implemented — see `PLAN.md`
  for phasing): a grounding layer (L5) that resolves every field to a verbatim,
  exact-substring-verified quote and page/character/bbox coordinates computed by code,
  never emitted by the model; a custom multi-page Schedule-of-Activities table stitcher
  (L2), since no available tool merges tables spanning multiple pages correctly; a
  completeness-accounting step (expected vs. found counts) as the direct defense against
  silent omission, the dominant failure mode on long documents; and a conformal-prediction
  bound on the auto-accepted field set, replacing the plan for a purely hand-tuned
  confidence formula.
- Vision-first SoA reframed as **specialist-grid + vision-LLM-content**: published
  evidence shows a 1.2B specialist table model beats frontier vision-LLMs on table
  *structure*, while vision-LLMs are stronger on *cell text* — no single model should own
  both.
- Recorded `usdm4`'s GPL-3.0 license as a deliberate, internal-use decision, and adopted
  `data4knowledge/usdm_data` (~20 real, CORE-validated studies with public source PDFs) as
  the ground-truth seed corpus in place of hand-labeling the 4 local protocol PDFs from
  scratch.
- Corrected a stale internal figure: an earlier spike's "0 of 235 protocols assembled"
  result is outdated against the currently vendored `usdm4` source, which already fixes
  two of that spike's "open" bugs. The real pass rate is unmeasured, not proven broken —
  re-measuring it is now Phase 0 of the roadmap.

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
