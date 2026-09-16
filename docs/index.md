# USDM4-Assure

**Convert clinical trial protocol PDFs into conformant CDISC USDM 4.0 JSON — with an
Assurance layer engineered to surpass the market accuracy ceiling (~89% field / ~76% SoA).**

USDM4-Assure is a Python pipeline that reads a protocol document and produces a
structurally-valid USDM 4.0 study spanning metadata, study design, eligibility,
objectives, interventions, and the Schedule of Activities — with every extracted
field provenance-tagged, cross-checked, and triaged for human review.

## Why it exists

Published protocol-to-USDM systems plateau at ~89% field-level accuracy because they
share four structural weaknesses. USDM4-Assure attacks each one directly:

| Market weakness | Our counter-mechanism |
|---|---|
| Single-path extraction | **Multi-method ensemble** — ≥2 independent paths per field |
| Uncalibrated confidence | **Grounded verifier + calibrated confidence** |
| SoA rebuilt from flat text | **Vision-first geometry** (read the grid, don't reconstruct it) |
| Static systems | **Closed-loop learning** from reviewer corrections |

See [Architecture](architecture.md) for how these map onto the code.

## The accuracy contract

"100% accuracy for clinical use" is a **human-in-the-loop certification guarantee**,
not zero-touch output. The pipeline maximizes *un-reviewed* accuracy, makes confidence
trustworthy so review is surgical, and blocks non-conformant output at the CORE gate.
The clinical guarantee comes from the Assurance layer + conformance gate + SME sign-off.

## Quickstart

```bash
# Python 3.12 is required (the CDISC stack has no 3.13 wheel yet).
conda create -n usdm4 python=3.12 -y
conda run -n usdm4 python -m pip install -e ".[dev]"

# Generate a synthetic protocol and run the full loop.
conda run -n usdm4 python spikes/make_full_fixture.py
conda run -n usdm4 python -m usdm4_assure.cli convert-full data/fixtures/protocol_full.pdf
```

No API keys and no real data are required to run the pipeline: the extraction ensemble
uses independent deterministic methods, and an LLM member (Claude) joins automatically
when `ANTHROPIC_API_KEY` is set. See [Development](development.md) for full setup.

## Documentation map

- **[Architecture](architecture.md)** — the seven layers and the market-beating design.
- **[Pipeline & contracts](pipeline.md)** — how data flows and the types each layer speaks.
- **[Module reference](modules.md)** — what every package does.
- **[Conformance & limitations](conformance.md)** — the validation gates, current results,
  and the honest analysis of what's gated by the upstream assembler.
- **[Development](development.md)** — setup, testing, and environment gotchas.
- **[References](references.md)** — standards, tools, and prior art.

## Status

A working, tested proof-of-concept: one protocol PDF → a structurally-valid USDM 4.0
study across six domains, 18 passing tests, fully Dockerized. Not yet CORE-clean — see
[Conformance](conformance.md) for exactly why and what remains.
