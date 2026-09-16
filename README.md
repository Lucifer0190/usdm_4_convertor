# USDM4-Assure

> Convert clinical trial protocol PDFs into conformant **CDISC USDM 4.0** JSON — with an
> **Assurance layer** engineered to surpass the market accuracy ceiling (~89% field / ~76% SoA).

**Status:** working proof-of-concept · **Python:** 3.12 · **License:** proprietary / internal (see [below](#license))

USDM4-Assure reads a protocol document and produces a structurally-valid USDM 4.0 study
spanning **metadata, study design, eligibility, objectives, interventions, and the
Schedule of Activities** — with every extracted field provenance-tagged, cross-checked by
independent methods, and triaged for human review. It runs with **no API keys and no real
data**: the extraction ensemble uses independent deterministic methods, and a Claude
member joins automatically when `ANTHROPIC_API_KEY` is set.

## Why

Published protocol-to-USDM systems plateau at ~89% because they share four weaknesses.
USDM4-Assure attacks each one directly (see [docs/architecture.md](docs/architecture.md)):

| Market weakness | Our counter-mechanism |
|---|---|
| Single-path extraction | **Multi-method ensemble** — ≥2 independent paths per field |
| Uncalibrated confidence | **Grounded verifier + calibrated confidence** |
| SoA rebuilt from flat text | **Vision-first geometry** — read the grid, don't reconstruct it |
| Static systems | **Closed-loop learning** from reviewer corrections *(planned)* |

The accuracy contract is a **human-in-the-loop certification guarantee**, not zero-touch
output: the pipeline maximizes un-reviewed accuracy, makes confidence trustworthy so
review is surgical, and blocks non-conformant output at the conformance gate.

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
  objectives, SoA), the **Assurance** layer (ensemble + verifier + calibrated confidence),
  and Integrity (assemble via data4knowledge + structural/d4k/CORE gates).
- A Claude adapter (tiered thinking) that is a drop-in ensemble member.
- 18 passing tests checking each domain against synthetic ground truth.
- Dockerized (`docker/`) for portability.

Planned: provenance review UI, closed-loop learning, Neo4j graph store, and the
conformance work described below.

## Documentation

Full docs in [`docs/`](docs/index.md):

- [Architecture](docs/architecture.md) — the seven layers and the market-beating design.
- [Pipeline & contracts](docs/pipeline.md) — data flow and the shared types.
- [Module reference](docs/modules.md) — what every package does.
- [Conformance & limitations](docs/conformance.md) — the gates, current results, and an
  honest analysis of what's gated by the upstream assembler.
- [Development](docs/development.md) — setup, testing, environment gotchas.
- [References](docs/references.md) — standards, tools, prior art.

Design and strategy background: [`DESIGN.md`](DESIGN.md),
[`spikes/SPIKE_LOG.md`](spikes/SPIKE_LOG.md).

## Conformance status (honest)

The full study is structurally valid and assembles with zero errors, but is **not yet
CORE-clean**. A significant share of the residual findings is gated by the **upstream
data4knowledge assembler** (e.g. it does not attach objectives to the study design), not
by our extraction. See [docs/conformance.md](docs/conformance.md) for the rule-by-rule
breakdown and the roadmap to close it.

## License

This project is **proprietary and internal to Hexaware (HTL practice)**. It is not
released under an open-source license. Do not redistribute without authorization.
*(If this repository is intended to be open-sourced, replace this section with the chosen
license and add a `LICENSE` file — that is a deliberate decision, so it is left explicit
here rather than assumed.)*
