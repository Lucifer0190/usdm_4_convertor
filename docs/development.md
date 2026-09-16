# Development

## Environment

**Python 3.12 is required.** The CDISC stack (`cdisc-rules-engine`, via `usdm4`) has no
Python 3.13 wheel yet and will try — and fail — to compile `pydantic-core` from Rust
source. Use a 3.12 environment.

```bash
conda create -n usdm4 python=3.12 -y
conda run -n usdm4 python -m pip install -e ".[dev]"
```

The project is also Dockerized (`docker/Dockerfile`, `docker-compose.yml`) targeting
`python:3.12-slim`, so the local PoC deploys unchanged elsewhere.

## API keys

Put keys in a `.env` file at the repo root (git-ignored); it is loaded automatically.
None are required to run the pipeline — the deterministic ensemble carries every run —
but they unlock additional capability.

| Variable | Unlocks |
|---|---|
| `OPEN_ROUTER_KEY` | **The default LLM gateway.** [OpenRouter](https://openrouter.ai) fronts many providers behind one key, so the ensemble can mix model families. The pipeline defaults to Claude (tiered: Haiku / Sonnet 4.5 / Opus 4.8). Override a tier with `OPENROUTER_MODEL_{HAIKU,SONNET,OPUS}`. |
| `OPENROUTER_SLM_MODEL` | The small-model member used with `--slm` (default `meta-llama/llama-3.1-8b-instruct`, ~$0.05/$0.08 per M). See [the SLM note](#the-slm-member) below. |
| `ANTHROPIC_API_KEY` | Fallback direct-Anthropic path, used only if no OpenRouter key is set. |
| `CDISC_LIBRARY_API_KEY` | The official CDISC CORE gate (`convert-full --core`) and controlled-terminology lookups. Free to register at the CDISC Library. |

The LLM resolution order is OpenRouter → direct Anthropic → stub (see `llm/router.py`).
With a key present, the Claude member joins the Assurance ensemble as an additional
independent path, which lifts agreement and auto-accept (e.g. metadata auto-accept went
from 1/6 to 5/6 on the reference fixture).

### The SLM member

Pass `--slm` to `convert` / `convert-full` to add a **small model as a second, different
family** in the metadata ensemble (default `meta-llama/llama-3.1-8b-instruct`). Off by
default for cost control.

> **Note:** OpenRouter hosts **no clinically fine-tuned model** (checked across 60
> providers / 411 models — the only "medical" hits are `mistral-medium`, a general
> model). We therefore use a small, cheap, medically-competent *general* model. Llama 3.1
> 8B is the design's cited choice (a distilled 8B beat its 70B teacher on
> eligibility-criteria extraction). A true clinical SLM would require fine-tuning — the
> Learning-layer path (reviewer corrections → SLM training data), not an off-the-shelf slug.

Why it helps: a different-family model that *independently agrees* with Claude is a
stronger signal than agreement between a model and a regex. On the reference fixture,
adding the SLM took metadata from 5/6 to **6/6 auto-accept** — the SLM and Claude
independently produced the same study title, resolving the one field that was in review.

### Tests never call a live model

`tests/conftest.py` sets `USDM4_NO_LLM=1`, which forces the router to the stub so the
suite stays fast, free, offline, and deterministic even when a key is present. Set the
same variable yourself to run the deterministic-only path from the CLI.

## Running

```bash
# generate synthetic fixtures (no real/sensitive protocol data needed)
conda run -n usdm4 python spikes/make_fixture.py        # metadata-only
conda run -n usdm4 python spikes/make_soa_fixture.py     # SoA table
conda run -n usdm4 python spikes/make_full_fixture.py    # full protocol

# run the CLI
conda run -n usdm4 python -m usdm4_assure.cli convert       data/fixtures/protocol_ABC123.pdf
conda run -n usdm4 python -m usdm4_assure.cli convert-soa   data/fixtures/protocol_soa.pdf
conda run -n usdm4 python -m usdm4_assure.cli convert-full  data/fixtures/protocol_full.pdf
```

## Testing

```bash
conda run -n usdm4 python -m pytest tests/ -q
```

The suite (18 tests) checks each domain's extraction against the fixtures' known ground
truth, the SoA cross-validation, and that the full loop assembles a structurally-valid
study. The first CORE-related import can be slow on a cold cache.

## Environment gotchas

- **`conda run` and multi-line `-c`**: `conda run -n env python -c "<multi-line>"` fails
  (`conda` rejects newline arguments). Always put throwaway scripts in a file and run the
  file. Scratch probes live under `spikes/` and are prefixed `_`.
- **Serializing assembled studies**: `wrapper.model_dump()` leaves `UUID`/enum objects in
  the dict; serialize with `json.dumps(obj, default=str)`.
- **d4k result objects**: `RulesValidationResults.passed` / `.count` / `.finding_count`
  are **properties, not methods** — read them defensively (see `validate/gate.py::_get`).

## Layout

```
src/usdm4_assure/   the package (see docs/modules.md)
tests/              pytest suite (ground-truth checks)
spikes/             fixtures (make_*.py), the spike log, and scratch probes (_*.py)
docs/               this documentation
docker/             Dockerfile; compose at repo root
DESIGN.md           the finalized architecture (design layer)
```

## Documentation site (optional)

The docs are plain Markdown and render on any Git host as-is. To serve them as a site,
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) is a good fit for a
CLI/developer product. An `mkdocs.yml` is provided; note that MkDocs core has slowed in
2026, so check the maintained fork your plugins target before committing to it.
