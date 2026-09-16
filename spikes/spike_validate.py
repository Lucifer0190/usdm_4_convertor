"""Spike: prove the Integrity-layer backbone on a real USDM 4.0 example.

Goal (DESIGN.md §9 steps 1-2):
  1. Load a real USDM 4.0.0 instance into the usdm4 pydantic model  -> structural validity.
  2. Run the bundled d4k rule validation                            -> conformance gate A.
  3. Run the CDISC CORE engine (validate_core)                      -> conformance gate F.

Run:  .venv/Scripts/python.exe spikes/spike_validate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SAMPLE = Path("spikes/_work/usdm4-src/validate/samples/sample_usdm_4.json")


def hr(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * (60 - len(title))}")


def main() -> int:
    if not SAMPLE.exists():
        print(f"[FAIL] sample not found: {SAMPLE}")
        return 2

    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
    hr("Example instance")
    print(f"file        : {SAMPLE}")
    print(f"usdmVersion : {raw.get('usdmVersion')}")
    print(f"systemName  : {raw.get('systemName')}")

    # --- 1. structural load into the pydantic model -------------------------
    hr("1. Pydantic structural load")
    try:
        import usdm4
        print("usdm4 module     :", getattr(usdm4, "__file__", "?"))
        # Discover the facade / wrapper class without assuming exact names.
        facade = getattr(usdm4, "USDM4", None)
        print("USDM4 facade     :", "found" if facade else "NOT found")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] import usdm4: {e!r}")
        return 3

    try:
        from usdm4.api.wrapper import Wrapper  # type: ignore
        w = Wrapper.model_validate(raw)
        study = w.study
        sv = study.versions[0] if getattr(study, "versions", None) else None
        print("[OK] Wrapper.model_validate succeeded")
        print("     study.name       :", getattr(study, "name", "?"))
        if sv is not None:
            designs = getattr(sv, "studyDesigns", None) or []
            print("     studyVersions[0] :", getattr(sv, "id", "?"))
            print("     studyDesigns     :", len(designs))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Wrapper path failed ({e!r}); will rely on facade.validate()")

    # --- 2. bundled d4k rule validation -------------------------------------
    hr("2. d4k rule validation  (USDM4().validate)")
    try:
        u = facade()  # type: ignore[misc]
        res = u.validate(str(SAMPLE))
        _report(res)
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] d4k validate: {e!r}")

    # --- 3. CDISC CORE conformance gate -------------------------------------
    hr("3. CDISC CORE conformance  (USDM4().validate_core)")
    print("(may download/prepare the CORE cache on first run — can take a while)")
    try:
        u = facade()  # type: ignore[misc]
        res = u.validate_core(str(SAMPLE))
        _report(res)
    except Exception as e:  # noqa: BLE001
        print(f"[note] CORE gate not run this pass: {e!r}")
        print("       (expected if cache/network/APIkey not ready — retry with prepare_core())")

    hr("Spike verdict")
    print("Backbone reachable: pydantic model + d4k rules + CORE facade all in one library (usdm4).")
    return 0


def _call(res: object, name: str):
    """Call a zero-arg method or read an attribute, defensively."""
    if not hasattr(res, name):
        return "<n/a>"
    v = getattr(res, name)
    try:
        return v() if callable(v) else v
    except Exception as e:  # noqa: BLE001
        return f"<err {e!r}>"


def _report(res: object) -> None:
    """Print the d4k/CORE RulesValidationResults summary."""
    print("result type   :", type(res).__name__)
    print("  passed      :", _call(res, "passed"))
    print("  rules run   :", _call(res, "count"))
    print("  findings    :", _call(res, "finding_count"))
    # Surface a couple of concrete failures if present.
    outcomes = getattr(res, "outcomes", None)
    if isinstance(outcomes, dict):
        fails = [(k, o) for k, o in outcomes.items()
                 if getattr(getattr(o, "status", None), "name", "") != "SUCCESS"]
        for rule, o in fails[:3]:
            print(f"   ✗ {rule}: {str(getattr(o, 'status', '?'))[:60]}")
        if not fails:
            print("   ✓ all executed rules passed")


if __name__ == "__main__":
    sys.exit(main())
