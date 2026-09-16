# Protocol → USDM 4.0 Conversion System — Finalized Technical Design (v0.2)

**Codename:** USDM4-Assure
**Status:** Finalized architecture for sign-off (build not yet started)
**Author:** Kirtikumar (Hexaware HTL) + Claude
**Date:** 2026-08-14
**Companion:** `usdm-4-executive-briefing.html` (strategy) · this doc = the build layer

---

## 0. The thesis — why this design beats the market

Every published system plateaus at **~89% field-level / ~76% SoA** accuracy (Banting Health, MITRE ProtocolMiner 22/29, Protocol2USDM). They fail for the **same four structural reasons**, and our architecture is designed to attack each one directly:

| # | Why the market plateaus | Our counter-mechanism | Design location |
|---|-------------------------|-----------------------|-----------------|
| 1 | **Single-path extraction** — one extractor per field, so its error = the system's error | **Multi-method ensemble** — every field extracted by ≥2 independent paths; agreement auto-accepts, disagreement routes to review | Assurance Layer §4.1 |
| 2 | **Uncalibrated confidence** — reviewers can't see which fields are risky, so errors slip past review | **Grounded verifier + calibrated confidence** — a critic model checks each value against its source span; confidence is measured, not guessed | Assurance Layer §4.2–4.3 |
| 3 | **SoA rebuilt from linearized text** — merged cells / multilevel headers destroyed | **Vision-first geometry, LLM-second semantics** — grid structure extracted deterministically from the image; LLM only labels | SoA sub-pipeline §3.C-SoA |
| 4 | **Static systems** — nobody learns from the SME's corrections | **Closed-loop learning** — every correction becomes a few-shot example, then SLM training data | Learning Layer §7 |

**The accuracy math.** Two independent extractors at ~89% each, with partially-independent errors, agree on ~80–85% of fields; on that agreed set, precision rises to ~97–99% (both must make the *same* mistake to fool it). The ~15–20% disagreement set is exactly what a human should review — so the SME reviews *less* and catches *more*. Certified output → clinically trustworthy (~100%), which is the real goal. **We don't beat the market by having a better model — we beat it by never trusting a single path and by measuring our own uncertainty honestly.**

---

## 1. The accuracy contract (unchanged, foundational)

"100% accuracy for clinical use" is achieved as a **human-in-the-loop certification guarantee**, not zero-touch output. The system's job is to (a) maximize *un-reviewed* accuracy, (b) make confidence trustworthy so review is surgical, and (c) block non-conformant output at the CORE gate. The clinical guarantee = Assurance Layer + CORE gate + SME certification. Any claim of zero-touch clinical output would be false and a regulatory risk.

---

## 2. Build strategy — fork, don't greenfield

**Decision: start from `Panikos/Protocol2USDM` + the `data4knowledge` libraries, then add the Assurance & Learning layers they lack.**

- `Protocol2USDM` already gives us: PDF parsing, vision SoA extraction, multi-model orchestration (Claude/Gemini/GPT), USDM v4.0 serialization. → our **Foundation + Extraction layers baseline**.
- `data4knowledge` (`usdm`, `usdm_data`, `study_definitions_workbench`, `ddf`) gives us: pydantic USDM model, **CORE validation**, Excel↔USDM, HTML render, Neo4j graph. → our **Integrity + Data layers plumbing**.
- **What no one has, and what we add = the moat:** the Assurance Layer (ensemble + verifier + calibrated confidence) and the Learning Layer (closed-loop from SME corrections).

First build task is a **spike** (§9) to validate these fork points on real example instances before committing.

---

## 3. Layered architecture

```
┌─ FOUNDATION ────────────────────────────────────────────────┐
│ A. Ingest & Layout   B. Route & Retrieve (RAG + section index)│  deterministic, cacheable
└──────────────────────────────────────────────────────────────┘
┌─ EXTRACTION ────────────────────────────────────────────────┐
│ C1..C7 domain extractors   +   C-SoA vision sub-pipeline      │  produces candidate USDM entities
└──────────────────────────────────────────────────────────────┘
┌─ ASSURANCE  ★ the differentiator ───────────────────────────┐
│ 4.1 Ensemble  4.2 Grounded verifier  4.3 Calibrated confidence│  turns candidates → scored, triaged fields
└──────────────────────────────────────────────────────────────┘
┌─ INTEGRITY ─────────────────────────────────────────────────┐
│ D. Entity Registry + reconcile  ·  Coded-value service (EVS)  │  UUID graph correct + no memory codes
│ E. Assemble  ·  F. Validate (pydantic + CORE gates)           │
└──────────────────────────────────────────────────────────────┘
┌─ CERTIFICATION ─────────────────────────────────────────────┐
│ G. Provenance review UI  ·  SME sign-off  ·  audit trail      │  the "100%" guarantee
└──────────────────────────────────────────────────────────────┘
┌─ LEARNING (closed loop) ────────────────────────────────────┐
│ 7. corrections → few-shot bank → eval set → SLM fine-tune     │  system improves per protocol
└──────────────────────────────────────────────────────────────┘
┌─ DATA (downstream, Phase 2) ────────────────────────────────┐
│ H. Neo4j property graph — amendment impact, SDTM automation   │
└──────────────────────────────────────────────────────────────┘
```

### Foundation

**A. Ingest & Layout (`ingest/`)** — `pymupdf` (text + coords + page-image render) + `pdfplumber` (table candidates). Output: `Document` = ordered blocks `{text, page, bbox, kind}` + rendered page PNGs (SoA needs these). No LLM — deterministic, cached.

**B. Route & Retrieve (`retrieve/`)** — section index over ICH M11-style headings; **header-preserving chunking** (never naive split); embeddings + top-k retrieval into focused domain prompts (RAG = +26 pts vs long-context, Banting). Tables bypass RAG → SoA sub-pipeline with page images.

### Extraction

**C1–C7 domain extractors (`extract/`)** — one module per USDM domain, run in dependency order, each consuming prior outputs as context. Each returns **pydantic USDM instances + provenance**, not loose dicts.

| # | Domain | Produces | Phase |
|---|--------|----------|-------|
| C1 | Metadata & identifiers | Study, StudyVersion, StudyIdentifier, Organization, StudyTitle | 1 |
| C2 | Design skeleton | StudyDesign, StudyArm, StudyEpoch, StudyCell, StudyElement | 1 |
| C3 | Population & eligibility (free text) | StudyDesignPopulation, EligibilityCriterion(+Item) | 1 |
| C4 | Objectives & endpoints | Objective, Endpoint | 1 (Estimand → 2) |
| C5 | Interventions | StudyIntervention, Administration, AdministrableProduct | 1 |
| C6 | Biomedical concepts | BiomedicalConcept, Activity | 1 |
| C-SoA | Schedule | ScheduleTimeline, Encounter, ScheduledActivityInstance, Timing, Condition, TransitionRule | 1 |
| C7 | Amendments | StudyAmendment, StudyAmendmentReason, ImpactedEntity | 2 |

**C-SoA — vision-first SoA sub-pipeline (`extract/soa/`)** — the safety-critical module. Attacks market failure #3:
1. **Geometry from vision, deterministically** — multimodal model returns the *grid*: header hierarchy (epoch→visit→week), row activities, **merged-cell spans as explicit spans**. We never ask it to rebuild the table from linearized text (the market's #1 SoA error).
2. **Value extraction** — cell values from layout-parsed table.
3. **Cross-validation** — reconcile vision-grid vs text; tag each cell `both`/`text-only`/`vision-only`/`none`. Disagreements surfaced, never auto-resolved.
4. **Semantic build** — ScheduledActivityInstance (activity×encounter×epoch), Timing (ISO-8601 windows), **Condition** for footnote-gated cells (footnote → predicate), TransitionRule for dose-escalation/cyclic logic. (Matches ProtocolMiner's relative-timing/window/conditional coverage — the parts it got right.)

### ★ Assurance Layer (`assure/`) — the moat

**4.1 Multi-method ensemble.** Every field is produced by **≥2 independent paths**, chosen per field type:
- prose fields → (a) Claude RAG extractor + (b) a second-family model (Gemini-Vertex/GPT) OR a second retrieval strategy;
- SoA cells → text-path + vision-path (already dual by construction);
- numeric/timing/dose fields → **self-consistency voting** (sample N=3–5, majority) because these are the highest-clinical-risk and cheapest to over-sample.
Agreement → auto-accept (high confidence). Disagreement → review queue with both candidates shown.

**4.2 Grounded verifier (critic).** A separate model call asks, for each accepted field: *"Is value V supported by source span S? {supported | partial | unsupported}"* — grounded in the retrieved text, never memory. `unsupported` → forced to review regardless of ensemble agreement. This is the dedicated hallucination catch, especially for numeric/timing.

**4.3 Calibrated confidence.** Confidence = f(ensemble agreement, verifier verdict, retrieval score, code-resolution status). Calibrated on the eval set so "90% confidence" means ~90% correct — *that* is what makes the review UI's triage trustworthy (attacks failure #2). Thresholds (auto-accept / review / block) are tunable per client risk appetite.

### Integrity

**D. Entity Registry & reconciliation (`registry/`)** — central UUID authority. Extractors **never invent UUIDs**; they resolve entities by natural key and get stable UUIDs back. Post-pass: dangling refs, orphans, type mismatches → flagged. This is what single-LLM approaches structurally cannot do.

**Coded-value service (`coding/`)** — every coded attribute (route, dose form, timing type, BC codes) via **NCI EVS + CDISC Library API**, cached. LLM may only propose the *search term*; unresolved → review, never guessed. Architectural invariant.

**E. Assemble (`assemble/`)** → compose registry entities into the full `Study` pydantic object.

**F. Validate (`validate/`)** — two blocking gates: (1) pydantic structural, (2) **CDISC CORE** via `cdisc-org/cdisc-rules-engine` (USDM 4.0 JSON-schema + Dec-2025 JSONata rules). Not certifiable until both pass or violations are SME-waived with audit reason. *Also use constrained/structured-output generation so schema-invalid JSON is impossible by construction.*

### Certification

**G. Review UI (`review/`)** — every field shows source (page/bbox), method (text/vision/both/ensemble), calibrated confidence, verifier verdict, CORE status. Sort by risk: disagreements, unsupported, vision-only, unresolved-code, and all numeric/timing float to top. SME edits write to the pydantic model; edit history = audit trail (who/what/when/prompt-version). **This is where "100%" is realized.** PoC = thin (annotated JSON + spreadsheet); Phase 2 = full web app.

### Learning (closed loop) — attacks failure #4

**7. Learning Layer (`learn/`)** — every SME correction is captured as a labeled `(source span → correct value)` pair. Uses:
- **few-shot bank** — corrections retrieved as in-context examples for similar future fields (immediate benefit, no training);
- **growing eval set** — every correction hardens the regression suite;
- **SLM fine-tuning (Phase 2)** — accumulated pairs train the narrow-task SLMs (eligibility categorization, terminology, entity normalization).
Net effect: **the system's un-reviewed accuracy rises with every protocol processed.** Static market tools cannot do this.

### Data (downstream, Phase 2)

**H. Graph store (`graph/`)** — Neo4j (reuse d4k's `ddf` loader). Flat JSON = exchange format; graph = operational store for amendment impact, cross-study benchmarking, protocol→SDTM via BiomedicalConcept. **Not in the extraction path** (GraphRAG adds latency, no extraction-accuracy gain).

---

## 4. Model orchestration — Claude-primary, tiered thinking, ensemble-diverse

Router (`llm/router.py`) picks model + thinking budget per task:

| Task | Model + thinking | Rationale |
|------|------------------|-----------|
| Cheap/narrow (term→search string, classification) | **Claude Haiku**, no extended thinking | high volume, low complexity |
| Prose domain extraction (C1–C6) | **Claude Sonnet**, light thinking | reasoning over scattered fields |
| SoA vision, reconciliation, verifier, hard eligibility | **Claude Opus + extended thinking** | hardest reasoning, highest clinical risk |
| Ensemble second path | **different family** (Gemini-Vertex / GPT-5) | error *independence* is the point — same model twice ≠ ensemble |
| Narrow high-volume (Phase 2) | **fine-tuned SLM** (Llama 3.1 8B), on-prem | cost + HIPAA data residency |

Rules: Gemini only via **Vertex AI enterprise BLOCK_NONE**. **All prompts version-controlled** (data4knowledge ran 60+ versions — treat prompts as production code). Router logs model+prompt-version per field into the audit trail.

---

## 5. Eval harness (`eval/`) — you can't surpass what you can't measure

You have no data, so bootstrapping is step 1:
1. **Ground truth v0** = example USDM instances in `DDF-RA` / `usdm_data` + their source protocols; confirm they pass our validators (smoke test + first labels).
2. **Field-level scorer** — UUID-normalized path flattening; per-domain weighted accuracy (Banting method) + CORE pass rate + **SoA per-cell accuracy separately** + **confidence calibration curve** (are we honest about our uncertainty?).
3. **Regression gate** — every prompt/model change re-runs eval; accuracy must not drop. Non-negotiable given prompt sensitivity.
4. **Beat-the-market scoreboard** — track our numbers vs the published ~89%/~76% with matched scope caveats.

---

## 6. Repository layout

```
usdm4_assure/
  ingest/        A — pdf → layout + page images
  retrieve/      B — chunking, embeddings, RAG, routing
  extract/       C1–C7 domain extractors
    soa/         C-SoA vision-first sub-pipeline
  assure/        ★ 4.1 ensemble · 4.2 verifier · 4.3 confidence
  registry/      D — UUID registry + reconciliation
  coding/        NCI EVS / CDISC Library lookup (+cache)
  assemble/      E — compose Study object
  validate/      F — pydantic + CORE gates + structured-output guards
  review/        G — provenance review UI (API + frontend)
  learn/         7 — correction capture, few-shot bank, SLM datasets
  graph/         H — Neo4j loader (Phase 2)
  llm/           router, provider adapters, versioned prompts
  eval/          harness, scorers, ground-truth, market scoreboard
  usdm_model/    vendored/pinned CDISC pydantic classes (d4k)
  tests/
  docker/        Dockerfile + compose (CORE engine, Neo4j, app)
```

Dockerized from day one (your requirement): PoC runs locally via `docker compose`, same image deploys anywhere.

---

## 7. Phased plan

**Phase 1 — PoC (6–8 wks):** Foundation + Extraction (C1–C6, C-SoA) + **full Assurance Layer** (this is the differentiator, not a nice-to-have) + Integrity + thin Certification UI + Eval. Eligibility as free text (defer AND/OR logic). Cloud Claude, tiered. Dockerized local. Target: **exceed 89% field / 76% SoA** on 3–5 protocols, with calibrated confidence.
**Phase 2:** Estimand, Amendments (C7), SLM fine-tuning + on-prem, Neo4j (H), full web review UI, GxP validation package, closed-loop learning at scale.

---

## 8. Decisions confirmed / defaults taken

- ✅ Design-first, then build. ✅ Python. ✅ **Claude primary, tiered thinking**; second family only for ensemble independence. ✅ PoC local + **Dockerized** for portability. ✅ No data → bootstrap from CDISC/`data4knowledge` examples + public ClinicalTrials.gov protocols.
- **Default taken (say if you disagree):** thin review UI for PoC; local FAISS/Chroma vector store; fork `Protocol2USDM` + `data4knowledge` as the baseline.

---

## 9. First build step — the spike (before any pipeline code)

Before committing to the fork, a 1–2 day spike to de-risk every assumption:
1. Clone `data4knowledge/usdm` + `DDF-RA`; load example USDM 4.0 instances into the pydantic model → confirm they validate.
2. Run `cdisc-org/cdisc-rules-engine` CORE against those instances locally, in Docker → confirm the gate works and we can read violations.
3. Clone `Panikos/Protocol2USDM`; run it on one public protocol PDF → see its raw output quality and where it stops (this defines exactly what our Assurance Layer must add).
4. Stand up the `docker compose` skeleton (app + CORE + Neo4j placeholder).

**Green light from the spike = the entire design is grounded in verified, runnable reality.** Then we build the ingest→assurance→validate spine on one protocol end-to-end, and only then scale to the 3–5 PoC protocols.

---

## Sources
Protocol2USDM (github.com/Panikos/Protocol2USDM) · data4knowledge repos (usdm, usdm_data, ddf, study_definitions_workbench) · CDISC DDF-RA, usdm_api, cdisc-rules-engine · Banting Health arXiv 2602.00052 · MITRE ProtocolMiner (esmed.org MRA 7362) · PHUSE ML08 SoA→USDM.
