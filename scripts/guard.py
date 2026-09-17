#!/usr/bin/env python3
"""CI guardrails — fail on empty packages, huge files, or hard-coded paths.

Exit 0 if all checks pass, 1 otherwise.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def check_empty_packages() -> list[str]:
    """Fail if any top-level package under src/ contains only __init__.py."""
    src = REPO_ROOT / "src"
    if not src.exists():
        return []

    errors = []
    for pkg_dir in src.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name == "__pycache__":
            continue
        init_file = pkg_dir / "__init__.py"
        if not init_file.exists():
            continue
        py_files = [f for f in pkg_dir.glob("*.py") if f.name != "__init__.py"]
        subdirs = [d for d in pkg_dir.iterdir() if d.is_dir() and d.name != "__pycache__"]
        if not py_files and not subdirs:
            errors.append(f"Empty package: {pkg_dir.relative_to(REPO_ROOT)}")
    return errors


def check_file_sizes() -> list[str]:
    """Fail if any .py file is >400 lines."""
    errors = []
    for py_file in (REPO_ROOT / "src").rglob("*.py"):
        lines = py_file.read_text(encoding="utf-8").split("\n")
        if len(lines) > 400:
            errors.append(f"Too large ({len(lines)} lines): {py_file.relative_to(REPO_ROOT)}")
    return errors


def check_hard_coded_paths() -> list[str]:
    """Fail if any .py file contains absolute paths like C:\\ or /home/."""
    errors = []
    for py_file in (REPO_ROOT / "src").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.split("\n"), 1):
            if "C:\\" in line or "/home/" in line:
                errors.append(
                    f"Hard-coded path at {py_file.relative_to(REPO_ROOT)}:{line_no}: "
                    f"{line.strip()[:50]}"
                )
    return errors


def main() -> int:
    errors = []
    errors.extend(check_empty_packages())
    errors.extend(check_file_sizes())
    errors.extend(check_hard_coded_paths())

    if errors:
        print("CI guardrails failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("CI guardrails passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
