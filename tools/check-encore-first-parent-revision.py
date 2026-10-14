#!/usr/bin/env python3
"""Prevent native revision regressions after long non-numbered commit streaks."""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[1]
script = (root / "tools/ci/derive-encore-build-label.py").read_text()
workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()

assert '["git", "-C", str(ROOT), "log", "--first-parent", "--format=%s"]' in script
assert '"-n", "256"' not in script
assert "fetch-depth: 0" in workflow
assert "fetch-depth: 256" not in workflow

derive = runpy.run_path(str(root / "tools/ci/derive-encore-build-label.py"))
build_label = derive["build_label"]
long_subjects = ["ci: routine source maintenance"] * 600
long_subjects += ["R458: final matched source revision", "R455: prior revision"]
assert build_label("\n".join(long_subjects)) == "R458"
assert build_label("R471: updated\nR460: older\nR469: another") == "R471"
try:
    build_label("ci: no revision in this source tree")
except ValueError as exc:
    assert "No numbered R revision" in str(exc)
else:
    raise AssertionError("Revision failure must not silently fall back to stale data")
print("FIRST_PARENT_HISTORY_LABEL_PASS fixture=600+ old_rev=458")
