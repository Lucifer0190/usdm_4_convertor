# Contributing

Guidelines for working on USDM4-Assure. See [docs/development.md](docs/development.md) for
environment setup.

## Ground rules

- **Python 3.12.** The CDISC stack has no 3.13 wheel yet. Use the `usdm4` conda env.
- **No real or sensitive protocol data in the repo.** Use the synthetic fixtures in
  `spikes/make_*.py`, which carry known ground truth so extraction can be scored.
- **Every extractor is scored against ground truth.** A new domain ships with a fixture
  and a test that asserts its output — not just that it runs.

## Adding a domain extractor

The architecture is additive (see [docs/pipeline.md](docs/pipeline.md)):

1. Create `extract/<domain>.py` returning `FieldCandidate`s and/or a small dataclass.
2. Run scalar fields through `assure.assure()` for the ensemble + verifier + confidence.
3. Map the assured output into the `AssemblerInput` in `assemble/study.py`.
4. Add a fixture section (or a new fixture) with ground truth, and a test in `tests/`.
5. Re-run the conformance report and note any rule changes in the [CHANGELOG](CHANGELOG.md).

Do **not** modify the Assurance layer or the gates to make a domain pass — that defeats
the point. If a value can't be verified, it should route to review, not be forced through.

## Code style

- **Docstrings:** Google style — a one-line summary, then `Args:` / `Returns:` / `Raises:`
  (in that order, blank-line separated). Public functions get full sections; small private
  helpers may use a single summary line.
- **Comments** explain *why*, not *what*. Prefer a short comment on a non-obvious choice
  over none.
- **Types** on every public signature. Keep line length ≤ 100 (`ruff` config in
  `pyproject.toml`).
- Run `ruff format` and `ruff check` before committing.

## Tests

```bash
conda run -n usdm4 python -m pytest tests/ -q
```

All tests must pass. When you change a prompt or a model, treat it as a potential accuracy
regression: re-run the suite and record the result.

## Scratch work

Throwaway probes go under `spikes/` prefixed with `_` (git-ignored). Do not leave them in
the tree. Remember: `conda run ... python -c "<multi-line>"` fails — put scripts in a file.

## Conformance changes

When a change affects the d4k/CORE findings, update
[docs/conformance.md](docs/conformance.md) with the new counts and, if a rule moves
between the "upstream-gated" and "we-can-fix" buckets, say so.
