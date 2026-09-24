# Module reference

The package lives under `src/usdm4_assure/`. This page tracks both what exists today and
the target v0.3 layout from [`../DESIGN.md`](../DESIGN.md) §6 — planned modules are marked
*(planned, vN.N)*, and each names the DESIGN.md layer it belongs to.

> **v0.3 note on stub packages.** v0.2 shipped seven empty 1-line placeholder packages
> (`registry/`, `coding/`, `learn/`, `graph/`, `retrieve/`, `review/`, `eval/`) to make the
> layer map visible in the tree. The evidence review flagged this as a real risk — it made
> the design doc look more built than the code was. Going forward, **a package is only
> created once it has real code**; this page lists planned modules by name and target
> location instead, and CI now fails on empty packages.

## L0 — Substrate

| Module | Role |
|---|---|
| `ingest/pdf.py` | `ingest()` — PDF → `Document` (positioned blocks + rendered page images + character-level bboxes) via PyMuPDF. Deterministic, no LLM. Character geometry is what L5 grounding resolves quotes against. |

## L1–L2 — Layout, tables, SoA stitching *(planned, v0.3 Phase 2)*

| Module | Role |
|---|---|
| `layout/docling_adapter.py` | Docling integration — page layout, reading order. |
| `layout/mineru_adapter.py` | MinerU2.5 integration — table grid structure (beats frontier VLMs on TEDS). |
| `soa/stitcher.py` | The multi-page Schedule-of-Activities stitcher — header-signature matching across pages, "(continued)" detection, column reconciliation. No existing tool does this; it is the architecture's declared risk centre. |

## L3 — Routing *(planned, v0.3 Phase 3; ported from prior-art ideas per `PLAN.md` §5)*

| Module | Role |
|---|---|
| `sections/graph.py` | Typed section graph: authority surfaces, `current` vs `historic` distinction. |
| `sections/fingerprint.py` | Study-family classification (11 documented protocol families as config data) driving route/prompt/expectation adaptation. |
| `sections/route_plan.py` | `StudyExtractionPlan` / `DomainRoutePlan` — primary/supporting/**prohibited** evidence scopes per domain, 4-axis scoping (study/phase/arm/region). |

## L4 — Extraction

| Module | Role |
|---|---|
| `extract/metadata.py` | **C1** — study title, acronym, sponsor, phase, identifiers, version. Two independent deterministic methods (`labels`, `titlepage`) plus an optional LLM member. |
| `extract/design.py` | **C2** — study type, intervention model, and arms (parsed from the randomization sentence), with arm types. |
| `extract/eligibility.py` | **C3** — inclusion/exclusion criteria (stored as free text per USDM), planned age range, sex. |
| `extract/objectives.py` | **C4** — primary/secondary objectives and endpoints (Estimands deferred to Phase 6). |
| `extract/soa/methods.py` | Two independent SoA table extractors (`pdfplumber`, `pymupdf`) plus a drop-in `vision` member — becomes the grid+content split described in DESIGN.md §3 L1 once L1/L2 land. |
| `extract/soa/crossval.py` | Cell-by-cell cross-validation → `AssuredGrid` with provenance tags. |
| `extract/soa/grid.py` | The SoA intermediate representation (`SoAGrid`, `AssuredCell`, `AssuredGrid`). |

*Under Phase 4 every call here will be sharded to <40 fields and use two-pass (free-text
reasoning, then constrained JSON) emission — see DESIGN.md §3 L4.*

## L5 — Grounding

| Module | Role |
|---|---|
| `ingest/geometry.py` | Per-page character-level geometry: glyph ↔ bbox mapping via PyMuPDF `get_text("rawdict")`. Character offsets in `Document.text_of(page)` directly index `Document.chars[page]` for deterministic quote resolution. |
| `ground/quote.py` | Resolves a candidate's verbatim quote to page + character offset + bounding box using character geometry. Pass 1: exact substring per page. Pass 2: normalized (whitespace collapse, ligatures, soft hyphens, smart quotes). Returns `Quote(text, verify_pass∈{exact,normalized,failed}, page, char_start, char_end, bbox)`. |
| `audit/store.py` | Append-only Part 11 audit store (SQLite). Every field decision logs model ID, prompt hash, quote text, verify_pass, page, and bbox for reproducibility and audit compliance. |

## L6 — Assurance ★

| Module | Role |
|---|---|
| `assure/__init__.py` | The moat. `assure()` groups candidates per field (ensemble), resolves grounding via L5, verifies each value against its source span, and computes confidence + `Decision`. Runs fully without an LLM on deterministic ensemble members; LLM is invoked only for verification on the uncertain subset. Uniform across C1–C4 and SoA. |
| `assure/verify.py` | Two-tier verifier: (1) deterministic token-overlap check (free); (2) escalation to a `verify`-role LLM (third family, different from extractor and alt-extractor) only when deterministic verdict is "partial". Hard gates: value with only failed quotes BLOCKs; value with ≥1 ok quote proceeds. |
| `extract/shards.py` | Shard definitions for two-pass LLM extraction: <40 fields per shard, organized by domain (C1–C4). Each shard has versioned `pass1.md` (reasoning) and `pass2.md` (JSON) templates. |
| `llm/two_pass.py` | Two-pass extraction orchestrator: pass 1 free-text reasoning, pass 2 strict JSON `[{field, value, quote}]` with mandatory verbatim quotes. `extract_shard()` returns `GroundedCandidate`s with resolved quotes. |
| `audit/writer.py` | Pipeline integration for audit logging: `write_field_decision()` appends one `AuditRecord` per `AssuredField`, pulling model/prompt/quote provenance from the winning grounded candidate. |
| `assure/confidence.py` *(planned, Phase 4)* | Multi-signal fitted confidence model (grounding outcome, entailment, cross-model agreement, field type, retrieval score) replacing the current hand-set formula. |
| `assure/conformal.py` *(planned, Phase 4)* | Split-conformal threshold with small-sample correction — a provable, marginal bound on error among auto-accepted fields. |
| `assure/completeness.py` *(planned, Phase 3)* | Expected-vs-found reconciliation per domain (visit/arm/activity counts) — the direct defence against silent omission. |

## L7 — Assembly

| Module | Role |
|---|---|
| `assemble/metadata.py` | Patch assured metadata into a minimal conformant USDM skeleton (used by the C1 spine). |
| `assemble/soa.py` | `AssuredGrid` → `TimelineInput` → USDM ScheduleTimeline entities via the data4knowledge `TimelineAssembler`. |
| `assemble/study.py` | Compose the full `AssemblerInput` from every domain and run the top-level `Assembler` → one USDM 4.0 study. |
| `assemble/sanitizer.py` *(planned)* | Enforces the Assembler's implicit input contract before `execute()` — no empty required strings, valid role keys, well-formed enrollment blocks. Sanitizer repairs are logged as quality findings. |
| `assemble/builder_fallback.py` *(planned)* | Per-section fallback to `usdm4.builder` when the Assembler errors on a section, with the run's assembler-reliance ratio recorded. |

## L8 — Validation

| Module | Role |
|---|---|
| `validate/gate.py` | The conformance gates: pydantic structural, d4k rule engine (offline), CDISC CORE (optional, needs API key). |
| `validate/rule_map.py` *(planned)* | Declarative `rule_id → (domain, field, repair action)` table bridging validation findings to targeted re-extraction. |
| `repair/loop.py` *(planned)* | Bounded (≤2 round) repair loop driven by `rule_map.py`; unresolved findings become `review`/`block`, never silently dropped. |

## L9 — Certification *(planned, v0.3 Phase 5)*

| Module | Role |
|---|---|
| `review/` | Provenance review UI — click-to-source evidence crops, SME sign-off. |
| `review/audit.py` | Part 11 audit trail: model+prompt version, timestamps, prior values, reason-for-change, signature meaning, per field. |

## Model orchestration

| Module | Role |
|---|---|
| `llm/base.py` | The `LLM` protocol and tiered model routing (`ModelTier`, `tier_for`). |
| `llm/claude.py` | Claude adapter — pinned model ids per tier, extended-thinking budgets; activates when `ANTHROPIC_API_KEY` is set. |
| `llm/openrouter.py` | OpenRouter gateway — one key, many models, tiered (Haiku/Sonnet/Opus-equivalent), overridable per role. The default LLM path. |
| `llm/router.py` | `get_llm()` resolves OpenRouter → direct Anthropic → stub; `get_slm()` returns a cheap different-family model for ensemble diversity. |

*Note: logprobs are never load-bearing here — OpenRouter does not guarantee every provider
returns them (Anthropic does not). See DESIGN.md §4.*

## Deferred (recorded, not stubbed)

Neo4j graph store, closed-loop SLM fine-tuning at scale, and Merkle/replay audit receipts
are deliberately deferred per `PLAN.md` §7 — they are valuable Phase-2+ investments, not
Phase-0/1 scope, and are not represented as empty packages in the tree.

## Orchestration & CLI

| Module | Role |
|---|---|
| `pipeline.py` | `run()` (metadata spine) and `run_full()` (full loop). Both now route all domains through the uniform `assure()` path and write `review.json` with page + bbox + verify_pass on every row. |
| `cli.py` | `usdm4 version` — print version. `usdm4 roles` — print active model roles from `config/models.yaml`. `usdm4 convert` (metadata spine), `convert-soa` (table-only), `convert-full` (all domains). All accept `--require-llm` to fail on missing API key and `--core` to run CDISC CORE gate. |
| `contracts.py` | Shared dataclasses: `Document`, `FieldCandidate` (legacy), `GroundedCandidate` (quote-backed), `Quote`, `CharSpan`, `AssuredField`, `Finding`, `AuditRecord`, `Decision`. |
