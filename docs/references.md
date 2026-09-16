# References

## Standards & governing bodies

- **CDISC USDM 4.0** — Unified Study Definitions Model, the target standard
  (June 2025). Digital Data Flow (DDF) initiative: <https://www.cdisc.org/ddf>
- **CDISC CORE** — the open conformance rules engine; USDM rules published as JSONata to
  the CDISC Library (December 2025). <https://www.cdisc.org/core>
- **ICH M11** — the global electronic protocol template USDM 4.0 aligns with.
- **NCI EVS** — the mandatory source of coded values (routes, dose forms, biomedical
  concept ids) for USDM.

## Tools we build on

- **`cdisc-org/DDF-RA`** — the DDF reference architecture: the USDM 4.0 schema, the
  implementation guide, and example instances.
- **`cdisc-org/usdm_api`** — the official USDM API as pydantic classes.
- **`cdisc-org/cdisc-rules-engine`** — the CORE engine (wrapped by `usdm4`).
- **`data4knowledge/usdm4`** (PyPI: `usdm4`) — the pydantic USDM 4.0 model, the `Assembler`
  / `TimelineAssembler`, the bundled d4k rule library, controlled-terminology cache, and
  the CORE facade. USDM4-Assure builds its Integrity layer on this package.
- **PyMuPDF** and **pdfplumber** — the two independent PDF/table engines behind the SoA
  ensemble.

## Prior art (protocol → USDM)

- **Banting Health** (arXiv 2602.00052, 2026) — RAG-based extraction; reported ~89%
  weighted field accuracy vs ~62.6% for a single long-context model.
- **MITRE ProtocolMiner** — Schedule-of-Activities extraction to FHIR/USDM; 22/29
  protocols fully correct.
- **`Panikos/Protocol2USDM`** — an earlier open-source PDF→USDM v4 pipeline (now private);
  originally informed the extraction-baseline strategy.

> Accuracy figures across teams are **not directly comparable** — different protocol sets,
> entity scopes, and ground-truth methods. Any number we publish must carry its specific
> scope and measurement method. There is no shared industry benchmark yet.

## Documentation conventions used here

- **Docstrings** follow the [Google Python style](https://google.github.io/styleguide/pyguide.html):
  a one-line summary, then `Args:` / `Returns:` / `Raises:` sections (in that order,
  blank-line separated).
- **Prose docs** are Markdown, readable on any Git host, optionally served with
  [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).
