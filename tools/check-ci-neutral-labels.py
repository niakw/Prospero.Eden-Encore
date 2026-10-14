#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Enforce neutral, user-facing CI steps and selected core test messages.

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
# Core host harness diagnostics are user-visible inside the source-preflight
# job. Keep human-facing progress text neutral, but do not rewrite required
# ABI names, source paths, license notices or original upstream identities.
message_files = (
    "tools/check-ps5-direct-pool-host.py",
    "tools/check-ps5-guest-system-buttons.py",
    "tools/check-heap-growth-diagnostics-host.py",
    "tools/check-heap-growth.py",
)
messages_checked = 0
for relative in message_files:
    source = (root / relative).read_text()
    for number, line in enumerate(source.splitlines(), 1):
        if not re.match(r"^\s*(?:print|puts)\s*\(", line):
            continue
        messages_checked += 1
        if blocked.search(line):
            offenders.append(f"{relative}:{number}: {line.strip()}")
    # Historical messages with brand names may not return through future refactors.
    assert "Sony mspace unmapping" not in source
    assert "Sony PS untouched" not in source
assert messages_checked >= 4, "No core test status messages inspected"

if offenders:
    raise SystemExit("CI_STEP_NAME_BRANDING_FAIL\n" + "\n".join(offenders))
assert count >= 35, "No meaningful workflow steps scanned"
print(f"CI_MESSAGES_NEUTRAL_PASS workflow_steps={count} core_test_messages={messages_checked}")
