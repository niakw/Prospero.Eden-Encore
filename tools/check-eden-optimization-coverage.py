#!/usr/bin/env python3
"""Count Encore-owned code files awaiting optimization TRIAGE, never tests.

"Remaining" here means no documented code edit or source-level
optimization decision during the current project pass. It is NOT the
number of files proven to require a patch. Validation is a separate axis.
"""
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"docs/EDEN_OPTIMIZATION_COVERAGE_2026-10-20.json"
STATE=json.loads(P.read_text())
assert STATE["schema_version"]==1
tracked=set(subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode().split("\0"))-{""}
suffixes={".c",".cpp",".cxx",".cc",".h",".hpp",".inc"}
owners={p for p in tracked
        if p.startswith(("headless/","src/","vendor/encore-active/"))
        and Path(p).suffix in suffixes}
entries=STATE["handled_paths"]
handled={x["path"] for x in entries}
assert len(entries)==len(handled),"duplicate optimization owner"
assert handled<=owners,sorted(handled-owners)
assert all(x["disposition"] in
           {"code_changed_in_batch","reviewed_without_new_code_edit"}
           and x["evidence"] for x in entries)
needs_review=owners-handled
count_by_status={x:sum(e["disposition"]==x for e in entries)
                 for x in {"code_changed_in_batch","reviewed_without_new_code_edit"}}
assert len(owners)==STATE["owned_code_count_at_snapshot"],("owned code inventory changed",len(owners),STATE["owned_code_count_at_snapshot"])
assert len(owners)==len(handled)+len(needs_review)
print("EDEN_OPTIMIZATION_REVIEW_BACKLOG_PASS",
      "owned_code="+str(len(owners)),
      "handled="+str(len(handled)),
      "code_touched="+str(count_by_status["code_changed_in_batch"]),
      "reviewed_without_change="+str(count_by_status["reviewed_without_new_code_edit"]),
      "remaining_to_triage="+str(len(needs_review)),
      "confirmed_remaining_code_changes=UNKNOWN",
      "native_console_validation=SEPARATE")
