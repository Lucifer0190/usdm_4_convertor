# USDM4-Assure

> Convert clinical trial protocol PDFs into conformant **CDISC USDM 4.0** JSON — every
> field grounded in a verifiable citation, scored by a calibrated confidence, and triaged
> for human review with a 21 CFR Part 11 audit trail.

**Status:** working proof-of-concept, mid-revision to the v0.3 architecture · **Python:**
3.12 · **License:** proprietary / internal (see [below](#license))

USDM4-Assure reads a protocol document and produces a structurally-valid USDM 4.0 study
spanning **metadata, study design, eligibility, objectives, interventions, and the
Schedule of Activities** — with every extracted field provenance-tagged, cross-checked by
independent methods, and triaged for human review. It runs with **no API keys and no real
data**: the extraction ensemble uses independent deterministic methods, and an LLM member
joins automatically via **OpenRouter** when a key is set (Claude direct also works).

## Why — and what changed

A published-literature review ([`PLAN.md`](PLAN.md)) corrected two assumptions this
project started with: there is no single "~89%/~76% market ceiling" to beat (the two
figures traced to different, non-comparable studies), and independent-looking extraction
paths are far more correlated than assumed (measured cross-model error correlation is
0.74–0.82, not near-zero). The honest state of the art on this task is ~89% field-level
accuracy, with **silent omission** — a confident, complete-looking result quietly missing
data — as the dominant failure mode on real, long protocols.

USDM4-Assure's v0.3 design targets that failure mode directly (see
[docs/architecture.md](docs/architecture.md) and [`DESIGN.md`](DESIGN.md)):

| What actually breaks published systems | Our counter-mechanism |
|---|---|
| Silent omission on long/wide schemas | **Sharded extraction** + **completeness accounting** |
| Ungrounded values | **Mandatory verbatim quote**, resolved to page/coordinates by code, never the model |
| Table structure destroyed, especially across pages | **Specialist grid model + VLM content pass** + a custom multi-page stitcher |
| Dishonest confidence | **Multi-signal calibrated confidence** + a **conformal bound** on auto-accepted fields |

The accuracy contract is a **human-in-the-loop certification guarantee**, not zero-touch
output: the pipeline maximizes un-reviewed accuracy, makes confidence trustworthy so
review is surgical, and blocks non-conformant output at the conformance gate. "Full-proof"
conversion is not a claim any published system — including this one — can support; grounded,
calibrated, auditable output is.

## Quickstart

```bash
# Python 3.12 is required (the CDISC stack has no 3.13 wheel yet).
conda create -n usdm4 python=3.12 -y
conda run -n usdm4 python -m pip install -e ".[dev]"

# Generate a synthetic protocol and run the full loop (no real data needed).
conda run -n usdm4 python spikes/make_full_fixture.py
conda run -n usdm4 python -m usdm4_assure.cli convert-full data/fixtures/protocol_full.pdf
```

### CLI

| Command | Does |
|---|---|
| `usdm4 convert <pdf>` | Metadata-only spine (C1) → partial study + provenance review. |
| `usdm4 convert-soa <pdf>` | Extract a Schedule of Activities → USDM ScheduleTimeline entities. |
| `usdm4 convert-full <pdf>` | Full loop → one USDM 4.0 study across six domains. Add `--core` for the official gate. |

## What's built

- Foundation (`ingest`), Extraction (C1 metadata, C2 design, C3 eligibility, C4
  objectives, SoA), the **Assurance** layer (ensemble + verifier + confidence), and
  Integrity (assemble via data4knowledge + structural/d4k/CORE gates).
- **OpenRouter** as the default LLM gateway (multi-model, tiered), with a direct-Anthropic
  fallback and a drop-in SLM ensemble member (`--slm`).
- 18 passing tests checking each domain against synthetic ground truth.
- Dockerized (`docker/`) for portability.

**In progress (v0.3, see [`PLAN.md`](PLAN.md) for the phased roadmap):** mandatory
verbatim-quote grounding with code-side coordinate resolution, a multi-page Schedule-of-
Activities stitcher, uniform assurance across all domains, a conformal confidence bound,
completeness accounting, the provenance review UI, and a Part 11 audit trail.

## Documentation

Full docs in [`docs/`](docs/index.md):

- [Architecture](docs/architecture.md) — the ten layers and the evidence behind each one.
- [Pipeline & contracts](docs/pipeline.md) — data flow and the shared types.
- [Module reference](docs/modules.md) — what every package does, current and planned.
- [Conformance & limitations](docs/conformance.md) — the gates, current results, and an
  honest analysis of what's gated by the upstream assembler.
- [Development](docs/development.md) — setup, testing, environment gotchas.
- [References](docs/references.md) — standards, tools, and prior art, with corrected
  citation scope.

Design and strategy background: [`DESIGN.md`](DESIGN.md) (v0.3 technical design),
[`PLAN.md`](PLAN.md) (the evidence review and roadmap behind it),
[`spikes/SPIKE_LOG.md`](spikes/SPIKE_LOG.md).

## Conformance status (honest)

The full study is structurally valid and assembles with zero errors, but is **not yet
CORE-clean**. A share of the residual findings is gated by the **upstream
data4knowledge assembler** — though how large a share is currently *unmeasured*, not
proven: an earlier "0 of 235 protocols assembled" figure is stale against the currently
vendored assembler version. See [docs/conformance.md](docs/conformance.md) for the
rule-by-rule breakdown and [`PLAN.md`](PLAN.md) Phase 0 for the re-measurement plan.

## License

This project is **proprietary and internal to Hexaware (HTL practice)**. It is not
released under an open-source license. Do not redistribute without authorization.

Note: the `usdm4` package we build on is **GPL-3.0**. Internal use is not distribution,
so this is workable, but it is recorded here as a deliberate decision rather than an
oversight — see [`docs/references.md`](docs/references.md).
*(If this repository is intended to be open-sourced, replace this section with the chosen
license and add a `LICENSE` file — that is a deliberate decision, so it is left explicit
here rather than assumed.)*
