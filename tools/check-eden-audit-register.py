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
    assert len(cells) == 8, (raw, len(cells))
    ident, priority, deps, source, symbols, state, evidence, acceptance = cells
    assert ident not in entries, ("duplicate", ident)
    assert priority in {"P0", "P1", "P2"}, (ident, priority)
    assert state in valid_states, (ident, state)
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
assert len(entries) >= 30, len(entries)
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
assert "bridge is still DISABLED" in doc
print("ENCORE_CORE_AUDIT_REGISTER_PASS", f"entries={len(entries)}",
      "statuses=" + ",".join(f"{key}:{state_totals[key]}" for key in sorted(valid_states)))
