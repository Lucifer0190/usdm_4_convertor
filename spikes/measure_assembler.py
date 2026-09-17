"""Phase 0 spike — measure conformance against the real usdm_data corpus.

DEVPLAN.md task 0.1 asks for a re-measured "assembler pass rate" to replace the
stale "0 of 235" figure noted in docs/conformance.md. Running this against the
cloned corpus (``spikes/_work/usdm_data``, gitignored) surfaces two findings
that correct the plan's own assumptions, in the same spirit as PLAN.md §1:

1. **usdm_data ships completed, pre-assembled USDM wrapper JSON**, not
   ``AssemblerInput``-shaped fixtures. There is nothing to feed
   ``usdm4.assembler.assembler.Assembler.execute()`` here, so this script
   cannot reproduce the old "N of 235 assembled successfully" measurement
   style. What it measures instead — and what is actually available and
   useful — is **gate conformance**: does each real study load structurally
   and pass the d4k rule engine under our pinned ``usdm4==0.29.0`` (PINS.md)?
   That is a fair, real-corpus substitute for "does our tooling handle real
   studies," which is what the stale figure was trying to answer.
2. **The corpus has far fewer USDM v4.0.0 studies than PLAN.md/DESIGN.md
   assumed.** Those docs cite "~20 real studies... CORE-validated" from
   ``data4knowledge/usdm_data``. A full walk of ``source_data/`` finds 15
   wrapper-shaped JSON files total, spanning USDM v2.11-v3.11-v4.0, and only
   **6 are v4.0.0** — 4 named real protocols (Alexion/CDISC Pilot/Eli
   Lilly/Sanofi) plus 2 synthetic fixtures under ``temporary/`` (devices,
   observational). This script prints that count explicitly so the "~20"
   claim gets corrected from a real measurement rather than repeated.

Usage::

    .venv/Scripts/python.exe spikes/measure_assembler.py [--core]

Writes ``spikes/reports/assembler_baseline.json``.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "spikes" / "_work" / "usdm_data" / "source_data"
REPORT_PATH = REPO_ROOT / "spikes" / "reports" / "assembler_baseline.json"


def _find_wrapper_files(root: Path) -> list[Path]:
    """Return every JSON file under ``root`` that looks like a USDM wrapper."""
    hits = []
    for path in glob.glob(str(root / "**" / "*.json"), recursive=True):
        p = Path(path)
        try:
            with p.open(encoding="utf-8") as f:
                head = json.load(f)
        except Exception:  # noqa: BLE001 — not JSON, or unreadable; skip
            continue
        if isinstance(head, dict) and "study" in head and "usdmVersion" in head:
            hits.append(p)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", action="store_true",
                         help="Also run the CDISC CORE gate (needs CDISC_LIBRARY_API_KEY).")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from usdm4_assure.validate.gate import validate_wrapper  # noqa: E402

    if not CORPUS_ROOT.exists():
        print(f"Corpus not found at {CORPUS_ROOT}. Clone it first:\n"
              f"  git clone --depth 1 https://github.com/data4knowledge/usdm_data.git "
              f"spikes/_work/usdm_data", file=sys.stderr)
        return 1

    all_files = _find_wrapper_files(CORPUS_ROOT)
    by_version: dict[str, int] = {}
    for p in all_files:
        with p.open(encoding="utf-8") as f:
            v = json.load(f).get("usdmVersion", "?")
        by_version[v] = by_version.get(v, 0) + 1

    v4_files = [p for p in all_files
                if json.load(p.open(encoding="utf-8")).get("usdmVersion", "").startswith("4.")]

    print(f"Corpus: {len(all_files)} wrapper-shaped JSON files total.")
    print(f"USDM version histogram: {by_version}")
    print(f"USDM v4.0.x files to gate: {len(v4_files)}")
    if len(v4_files) < 20:
        print(
            f"NOTE: PLAN.md/DESIGN.md cite '~20 real USDM v4.0 studies' from this corpus. "
            f"The real count is {len(v4_files)}. This is a correction to record, not a "
            f"silent adjustment — see this script's docstring.",
            file=sys.stderr,
        )

    results = []
    rule_failures: dict[str, int] = {}
    n_structural_pass = 0
    n_d4k_pass = 0

    for p in v4_files:
        wrapper = json.loads(p.read_text(encoding="utf-8"))
        report = validate_wrapper(wrapper, run_core=args.core)
        structural_ok = bool((report.get("structural") or {}).get("passed"))
        d4k = report.get("d4k") or {}
        d4k_ok = bool(d4k.get("passed"))
        if structural_ok:
            n_structural_pass += 1
        if d4k_ok:
            n_d4k_pass += 1
        for rule in d4k.get("failed_rules") or []:
            rule_failures[rule] = rule_failures.get(rule, 0) + 1
        results.append({
            "file": str(p.relative_to(REPO_ROOT)),
            "structural_passed": structural_ok,
            "d4k_passed": d4k_ok,
            "d4k_findings": d4k.get("findings"),
            "d4k_failed_rules": d4k.get("failed_rules"),
            "core": report.get("core"),
        })

    n = len(v4_files)
    summary = {
        "corpus_root": str(CORPUS_ROOT.relative_to(REPO_ROOT)),
        "usdm4_pin": "0.29.0 (see PINS.md)",
        "total_wrapper_files_all_versions": len(all_files),
        "version_histogram": by_version,
        "v4_files_measured": n,
        "structural_pass_rate": f"{n_structural_pass}/{n}",
        "d4k_pass_rate": f"{n_d4k_pass}/{n}",
        "rule_failure_histogram": dict(
            sorted(rule_failures.items(), key=lambda kv: -kv[1])
        ),
        "corpus_size_note": (
            f"PLAN.md/DESIGN.md cite '~20 real studies'; measured count of USDM v4.0.x "
            f"files in usdm_data is {n}, of which 4 are named real protocols "
            f"(Alexion/CDISC Pilot/Eli Lilly/Sanofi) and 2 are synthetic (devices, "
            f"observational) under source_data/temporary/. Docs should be corrected to "
            f"reflect this, not the assumed figure."
        ),
        "results": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nStructural pass rate: {n_structural_pass}/{n}")
    print(f"d4k pass rate: {n_d4k_pass}/{n}")
    print(f"Report written to {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
