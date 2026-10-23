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
records = []
for raw in table.splitlines():
    if not re.match(r"^\|\s*[A-Z][0-9]{2,3}\s*\|", raw):
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
    records.append((priority, source, len(symbols_list), state))
assert len(entries) >= 62, len(entries)
# F01's selected descriptor-queue helper was renamed when its capacity
# check became exact. Audit entries must follow compiled symbols, not stale
# source-count snapshots that quietly block all host/native CI gates.
v42 = next((line for line in table.splitlines() if line.startswith("| V42 |")), "")
assert "PreflightExactGuestDraw" in v42 and "PreflightLargeGuestDraw" not in v42
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


# The summary table is computed from the actual rows, not from a stale
# manually maintained snapshot. A new owner must update both layers at once.
def coverage(rows):
    return (len(rows), len({source for _, source, _, _ in rows}),
            sum(symbols for _, _, symbols, _ in rows))

def expect_coverage(label, rows, bold=False):
    numbers = coverage(rows)
    if bold:
        values = " | ".join(f"**{number}**" for number in numbers)
    else:
        values = " | ".join(str(number) for number in numbers)
    expected = f"| {label} | {values} |"
    assert expected in doc, ("stale quantified audit summary", expected, numbers)

expect_coverage("Graphe connu", records)
expect_coverage("HOST — preuve ciblée hôte", [r for r in records if r[3] == "HOST"])
expect_coverage("SOURCE — lecture effectuée, preuve insuffisante",
                [r for r in records if r[3] == "SOURCE"])
expect_coverage("OPEN — question technique non résolue",
                [r for r in records if r[3] == "OPEN"])
expect_coverage("PARKED — expérimentation suspendue",
                [r for r in records if r[3] == "PARKED"])
pending = [r for r in records if r[3] in {"SOURCE", "OPEN"}]
expect_coverage("**Encore à qualifier (SOURCE + OPEN)**", pending, bold=True)
expect_coverage("Dont priorité P0 (SOURCE + OPEN)",
                [r for r in pending if r[0] == "P0"])
pcount, pfiles, psymbols = coverage(pending)
assert f"{pcount} critères répartis sur\\n{pfiles} fichiers et {psymbols} mentions".replace("\\n", "\n") in doc
assert f"{state_totals['OPEN']} OPEN et {state_totals['SOURCE']} SOURCE." in doc

assert "bridge is still DISABLED" in doc
print("ENCORE_CORE_AUDIT_REGISTER_PASS", f"entries={len(entries)}",
      "statuses=" + ",".join(f"{key}:{state_totals[key]}" for key in sorted(valid_states)))
