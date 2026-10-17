#!/usr/bin/env python3
"""Fail if the active C/C++ source catalogue drifts from tracked files.

This verifies file-level coverage and exact graph cross-links only.
It is not a function audit, compiler check or console-test certificate.
"""
from pathlib import Path
import json
import re

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active"
document = (root / "docs/EDEN_ACTIVE_SOURCE_CATALOG.md").read_text()
audit = (root / "docs/EDEN_CORE_AUDIT_DEPENDENCIES.md").read_text()
begin, end = "<!-- ACTIVE_SOURCE_CATALOG_START -->", "<!-- ACTIVE_SOURCE_CATALOG_END -->"
assert document.count(begin) == document.count(end) == 1
section = document.split(begin, 1)[1].split(end, 1)[0]
suffixes = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inc", ".inl", ".s", ".S", ".asm"}
physical = sorted(
    p.relative_to(active).as_posix()
    for p in active.rglob("*")
    if p.is_file() and p.suffix in suffixes
)
graph = {}
for line in audit.splitlines():
    if not re.match(r"^\\| [A-Z][0-9]{2} \\|", line):
        continue
    fields = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(fields) < 4 or not fields[3].startswith("vendor/encore-active/"):
        continue
    relative = fields[3].removeprefix("vendor/encore-active/")
    graph.setdefault(relative, []).append(fields[0])
def role(path):
    if path.startswith("eden-backports/"):
        return "shipping-backport"
    if path.startswith("ps5-mesa/"):
        return "driver-fork"
    return "maintained-override"
expected = [
    f"| `{path}` | `{role(path)}` | {','.join(graph[path]) if path in graph else '—'} |"
    for path in physical
]
present = [line for line in section.splitlines() if line.startswith("| `")]
assert present == expected, (
    "Active source catalogue stale or exact graph linkage changed",
    len(present), len(expected),
    next(((a, b) for a, b in zip(present, expected) if a != b), None),
)
# The shipping backport manifest also carries two build recipes that are not
# C/C++ source files; track them explicitly rather than silently omitting them.
manifest = json.loads((active / "eden-backports/manifest.json").read_text())
shipping = set(manifest["entries"])
shipping_cpp = {"src/" + p.removeprefix("eden-backports/src/")
                for p in physical if p.startswith("eden-backports/src/")}
build_recipes = {"src/common/CMakeLists.txt", "src/core/CMakeLists.txt"}
assert shipping == shipping_cpp | build_recipes, (
    "Shipping backport source/build manifest coverage drift",
    sorted(shipping ^ (shipping_cpp | build_recipes)),
)
assert len(shipping) == 83 and len(manifest["shipping_receipts"]) == 43
assert manifest["excluded_experimental"] == ["EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS"]
assert len(physical) == len(set(physical))
print("ENCORE_ACTIVE_SOURCE_CATALOG_PASS",
      f"files={len(physical)}",
      f"graph_exact={sum(path in graph for path in physical)}",
      f"unlinked={sum(path not in graph for path in physical)}",
      f"shipping_sources={len(shipping_cpp)}",
      f"shipping_build_recipes={len(build_recipes)}")
