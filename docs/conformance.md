# Conformance & limitations

This page documents the validation gates, the current results on the reference fixture,
and an honest analysis of what is and isn't achievable today — including the parts gated
by the upstream assembler rather than by our extraction.

## The three gates

`validate/gate.py` runs up to three gates against an assembled study:

1. **Structural (pydantic)** — the study must load into the `usdm4` pydantic model.
   Non-negotiable; if it fails, the rule gates are skipped because they need a valid tree.
2. **d4k rule engine** — the bundled data4knowledge rule library (213 rules). Runs
   **offline**, no API key. This is the day-to-day gate.
3. **CDISC CORE** — the official engine (`cdisc-rules-engine`), wrapped by `usdm4`.
   Optional; requires a free `CDISC_LIBRARY_API_KEY` to download rules + controlled
   terminology. Enable with `convert-full --core`.

## Current results (reference fixture)

Running `convert-full` on `spikes/make_full_fixture.py` (a synthetic protocol spanning
metadata, design, eligibility, objectives, and a Schedule of Activities):

| Metric | Value |
|---|---|
| Structural gate | **PASS** |
| Assembler errors | **0** |
| d4k findings | **22** (down from 24 before C3/C4) |
| d4k failing rules | **12** (down from 14) |
| Entities | 3 arms, 3 epochs, 5 encounters, 5 activities, 5 scheduled instances |
| Phase | resolved to CDISC `C15601` (Phase II Trial) |

Adding domains demonstrably clears rules: `DDF00097` (planned age range) cleared by the
eligibility demographics, and `DDF00213` (interventions expected for a parallel design)
cleared by the derived interventions.

## Why the study is not yet CORE-clean — and where the blocker is

The residual d4k findings split into three buckets. **Critically, a large share is gated
by the upstream data4knowledge assembler, not by our extraction layer.** This is
confirmed by the assembler's own integration test
(`tests/usdm4/integration/test_assembler_to_core.py`), which pins a set of known-failing
rules on its minimum fixture.

### Bucket 1 — Upstream assembler gaps (cannot be fixed from our input)

| Rule(s) | Requirement | Status |
|---|---|---|
| `DDF00084`, `DDF00041` | Exactly one primary objective / at least one primary endpoint | We extract a valid objective + endpoint and pass them in correctly, but the assembler does **not** attach objectives to the study design (`studyDesign.objectives == 0`). |
| `DDF00172`, `DDF00201` | Exactly one sponsor study identifier / sponsor study role | Sponsor `StudyRole` emission is a known assembler gap. |
| `DDF00101` | An interventional study references an intervention from a procedure | Requires activity `definedProcedures` to reference interventions — not wired by the assembler. |

### Bucket 2 — Domains needing richer data we do not extract yet

| Rule(s) | Requirement |
|---|---|
| `DDF00006`, `DDF00025`, `DDF00031` | SoA timing windows / fixed reference timing types / relative anchors |
| `DDF00075` | `biomedicalConceptIds` on activities |
| `DDF00153` | A planned duration for the main timeline |

### Bucket 3 — Structural

| Rule(s) | Requirement |
|---|---|
| `DDF00087`, `DDF00088` | Linked-list ordering integrity (`previousId` / `nextId`) |

## Implication for the roadmap

To reach CORE-clean output, the work is **not** in the AI extraction layer (which is
producing valid, correct content). It is one of:

1. **Contribute fixes upstream** to the data4knowledge assembler (objective attachment,
   sponsor role emission, procedure→intervention references); or
2. **Construct the affected USDM parts ourselves** via the lower-level `usdm4.builder`,
   bypassing the assembler for those entities — a larger, self-contained effort to budget;
   and
3. **Extract the remaining data** (SoA timing windows, biomedical concepts, timeline
   duration) to satisfy Bucket 2.

This is exactly the kind of maturity risk a proof-of-concept exists to surface: the
pipeline architecture is sound and the extractors work; full conformance depends partly
on the maturity of the open-source assembler we build on.

## Defining "conformant" honestly

Even CDISC's own USDM 4.0 sample fails 18 d4k rules. "Zero findings" is therefore not the
right bar for a single protocol in isolation. The right targets, per the project design,
are a **CORE pass rate against a pinned rule set + version**, with rules split into
*extraction-relevant* vs *narrative/display*, and a documented human-review step for the
remainder. See [References](references.md).
