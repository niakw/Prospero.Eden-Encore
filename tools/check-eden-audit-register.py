#!/usr/bin/env python3
"""Check the single native audit register for stale files, symbols and cycles.

An existence/graph check, NOT a hardware or runtime correctness certificate.
"""
from collections import Counter
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
doc = (root / "docs/EDEN_CORE_AUDIT_DEPENDENCIES.md").read_text()
begin, end = "<!-- AUDIT_ROWS_START -->", "<!-- AUDIT_ROWS_END -->"
assert doc.count(begin) == doc.count(end) == 1
table = doc.split(begin, 1)[1].split(end, 1)[0]
valid_states = {"HOST", "SOURCE", "OPEN", "PARKED"}
entries = {}
state_totals = Counter()
for raw in table.splitlines():
    if not re.match(r"^\|\s*[A-Z][0-9]{2}\s*\|", raw):
        continue
    cells = [item.strip() for item in raw.strip().strip("|").split("|")]
    assert len(cells) == 9, (raw, len(cells))
    ident, priority, deps, source, symbols, state, evidence, acceptance, visual = cells
    assert ident not in entries, ("duplicate", ident)
    assert priority in {"P0", "P1", "P2"}, (ident, priority)
    assert state in valid_states, (ident, state)
    if state == "HOST":
        assert "img.shields.io/badge/" in visual and "2ea44f" in visual, ident
    else:
        assert "img.shields.io/badge/" not in visual, ident
    assert acceptance not in {"", "-", "TODO", "TBD"}, ident
    source_path = root / source
    evidence_path = root / evidence
    assert source_path.is_file(), (ident, "missing source", source)
    assert evidence_path.is_file(), (ident, "missing evidence", evidence)
    body = source_path.read_text()
    symbols_list = [term.strip() for term in symbols.split(";")]
    assert all(symbols_list), (ident, symbols)
    for symbol in symbols_list:
        assert symbol in body, (ident, source, "missing symbol", symbol)
    entries[ident] = [d.strip() for d in deps.split(",") if d.strip() != "-"]
    state_totals[state] += 1
assert len(entries) >= 58, len(entries)
assert doc.count("img.shields.io/badge/") >= 28
for ident, deps in entries.items():
    assert len(deps) == len(set(deps)), ("repeated dependency", ident)
    for dep in deps:
        assert dep in entries and dep != ident, (ident, dep)

visiting, done = set(), set()
def visit(ident):
    if ident in done:
        return
    assert ident not in visiting, ("cycle", ident)
    visiting.add(ident)
    for prerequisite in entries[ident]:
        visit(prerequisite)
    visiting.remove(ident)
    done.add(ident)
for ident in entries:
    visit(ident)

for ident in ("Q01", "T01", "T02", "J01", "H01", "H03", "V02", "V04", "M02", "S02"):
    assert ident in entries
# Every green historic test must point to a real file actually run by CI.
# Presence of a green badge does NOT imply console-game validation.
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
completed_rows = re.findall(r"^\| C\d\d \|.*$", doc, re.M)
assert len(completed_rows) >= 19
for row in completed_rows:
    assert row.count("img.shields.io/badge/") == 1, row[:60]
    assert "2ea44f" in row, row[:60]
    match = re.search(
        r"https://github\.com/niakw/Prospero\.Eden-Encore/blob/dev/ps5-sparse-jit/(tools/[^)]*\.py)",
        row,
    )
    assert match, ("missing hosted test link", row[:65])
    relative = match.group(1)
    assert (root / relative).is_file(), relative
    assert ("python3 -B " + relative) in workflow, ("green but not in CI", relative)

assert "bridge is still DISABLED" in doc
print("ENCORE_CORE_AUDIT_REGISTER_PASS", f"entries={len(entries)}",
      "statuses=" + ",".join(f"{key}:{state_totals[key]}" for key in sorted(valid_states)))
