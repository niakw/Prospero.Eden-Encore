#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Enforce neutral, user-facing CI step labels only.

Do not touch immutable third-party attribution, legal notices, required
source/toolchain identifiers, or artifact names consumed by automation.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
blocked = re.compile(r"\b(?:Sony|Nintendo|PlayStation|Switch[12]?|PS[345]|Xbox|Nvidia|AMD|Mesa|Microsoft)\b", re.I)
offenders = []
count = 0
for workflow in sorted((root / ".github/workflows").glob("*.yml")):
    for number, line in enumerate(workflow.read_text().splitlines(), 1):
        # Only the human-facing descriptions of steps, never IDs or filenames.
        match = re.match(r"^\s*-\s+name:\s*(.*?)\s*$", line)
        if not match:
            continue
        count += 1
        if blocked.search(match.group(1)):
            offenders.append(f"{workflow.relative_to(root)}:{number}: {match.group(1)}")
if offenders:
    raise SystemExit("CI_STEP_NAME_BRANDING_FAIL\n" + "\n".join(offenders))
assert count >= 35, "No meaningful workflow steps scanned"
print(f"CI_STEP_NAME_NEUTRAL_PASS scanned={count} workflows={len(list((root / '.github/workflows').glob('*.yml')))}")
