#!/usr/bin/env python3
"""Derive the native launcher's R revision from first-parent Git commit subjects.

MEMORY.md is a historical engineering log and can lag behind the source.
Never silently fall back to its latest heading: a stale footer is worse than
failing the native build with an actionable diagnostic. Walk all first-parent
subjects: documentation and CI commits may exceed the old 256-commit cutoff.

For host regression tests, a single optional path contains newline-separated
commit subjects (newest first), using exactly the same R-prefix matching.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REVISION = re.compile(r"^R([0-9]{2,6})(?=[: -]|$)")


def build_label(subjects: str) -> str:
    numbers = [
        int(match.group(1))
        for subject in subjects.splitlines()
        if (match := REVISION.match(subject.strip()))
    ]
    if not numbers:
        raise ValueError("No numbered R revision in Git history; fetch more first-parent commits")
    return f"R{max(numbers)}"


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit("Usage: derive-encore-build-label.py [fixture-subjects.txt]")
    if len(sys.argv) == 2:
        subjects = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--first-parent", "--format=%s"],
            check=True, capture_output=True, text=True,
        )
        subjects = proc.stdout
    try:
        print(build_label(subjects))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
