# Architecture

USDM4-Assure is organized as seven layers. Data flows top to bottom; each layer speaks
only in the shared contracts from `usdm4_assure.contracts`, which is what lets the
Assurance layer treat any extractor's output uniformly.

```
┌─ FOUNDATION ───────────────────────────────────────────────┐
│ ingest/  → PDF to positioned text blocks + page images      │  deterministic, cacheable
│ retrieve/ (planned) → section index, RAG chunking           │
└─────────────────────────────────────────────────────────────┘
┌─ EXTRACTION ───────────────────────────────────────────────┐
│ extract/  → one module per USDM domain (C1..C4, SoA)        │  produces candidate values
│ extract/soa/ → vision-first Schedule-of-Activities          │
└─────────────────────────────────────────────────────────────┘
┌─ ASSURANCE ★ (the moat) ───────────────────────────────────┐
│ assure/  → ensemble · grounded verifier · calibrated conf.  │  candidates -> scored, triaged
└─────────────────────────────────────────────────────────────┘
┌─ INTEGRITY ────────────────────────────────────────────────┐
│ assemble/ → compose USDM entities (via data4knowledge)      │
│ validate/ → structural + d4k + CORE conformance gates       │
│ coding/ (planned) → NCI/CDISC coded-value lookup            │
└─────────────────────────────────────────────────────────────┘
┌─ CERTIFICATION ────────────────────────────────────────────┐
│ review/ (planned) → provenance UI, SME sign-off, audit      │  the "100%" guarantee
└─────────────────────────────────────────────────────────────┘
┌─ LEARNING (planned) ───────────────────────────────────────┐
│ learn/  → corrections -> few-shot bank -> SLM datasets      │  improves per protocol
└─────────────────────────────────────────────────────────────┘
┌─ DATA (planned, downstream) ───────────────────────────────┐
│ graph/  → Neo4j property graph for SDTM automation          │
└─────────────────────────────────────────────────────────────┘
```

## The four market-beating mechanisms

The published state of the art plateaus at ~89% field / ~76% SoA because systems share
four weaknesses. Each has a concrete counter in this codebase:

### 1. Multi-method ensemble (vs single-path extraction)

Every field is produced by **≥2 independent methods** so that no single extractor's
error becomes the system's error. Agreement auto-accepts; disagreement routes to review.

- Metadata (C1): a label-driven parser and a title-page layout parser (`extract/metadata.py`).
- SoA: two independent table engines — `pdfplumber` (ruling lines) and PyMuPDF's
  `find_tables()` — reconciled cell-by-cell (`extract/soa/`).
- An LLM member (Claude) joins as an additional path when a key is present.

Because two independent extractors must make the *same* mistake to fool the ensemble,
precision on the agreed set rises well above either path alone.

### 2. Grounded verifier + calibrated confidence (vs uncalibrated confidence)

`assure/` checks each chosen value against the source span it was drawn from, and scores
confidence from agreement + verifier verdict + method count. The confidence is *measured*,
so the review triage (auto_accept / review / block) is trustworthy — reviewers spend
attention where clinical risk is highest.

### 3. Vision-first SoA geometry (vs reconstruction from flat text)

The Schedule of Activities never routes through the prose extractor. Table geometry is
read from the table structure directly (two independent engines), so merged headers and
footnote-gated cells survive. A multimodal LLM member is a drop-in third path.

### 4. Closed-loop learning (planned)

Every reviewer correction becomes a few-shot example and, later, SLM training data — so
un-reviewed accuracy rises with each protocol. No competitor does this today.

## Assemble on the ecosystem, don't reinvent it

USDM4-Assure builds the USDM entities through the **data4knowledge `usdm4`** package
(`assemble/`), which provides:

- the pydantic USDM 4.0 model (structural validation for free),
- the `Assembler` / `TimelineAssembler`, which mint conformant entities and resolve CDISC
  codes offline via a bundled controlled-terminology cache,
- the d4k rule engine and a wrapper around the official CDISC CORE engine (`validate/`).

Our own value is the **Assurance layer** and the domain **extractors** — the parts that
turn a PDF into structured, scored candidates. The [Conformance](conformance.md) page
covers where the upstream assembler's current limits become ours.

## The shared contracts

Everything between layers is one of a small set of dataclasses in
`usdm4_assure.contracts` (plus the SoA grid types in `extract/soa/grid.py`). See
[Pipeline & contracts](pipeline.md).
