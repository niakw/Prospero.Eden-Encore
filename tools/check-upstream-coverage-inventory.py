#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail when a pinned dependency has no corresponding upstream gap record.

This only checks inventory completeness; it does not validate that every
source change was reviewed or that any game bug was corrected.
"""
from pathlib import Path
import json
import re

root = Path(__file__).resolve().parents[1]
items = json.loads((root / "tools/deps.json").read_text())["items"]
names = [x["name"] for x in items]
assert len(names) == len(set(names)), "Duplicate dependency manifests"
report = (root / "docs/UPSTREAM_GAP_REGISTER_2026-10-14.md").read_text()
found = re.findall(r"^\| `([^`]+)` \|", report, re.M)
missing = sorted(set(names) - set(found))
unknown = sorted(set(found) - set(names))
if missing or unknown:
    raise SystemExit(f"UPSTREAM_INVENTORY_INCOMPLETE missing={missing} stale={unknown}")
assert "not a claim" in report and "API cap" in report
print(f"UPSTREAM_GAP_INVENTORY_PASS pinned={len(names)} registered={len(found)}")
