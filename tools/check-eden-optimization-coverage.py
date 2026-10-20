#!/usr/bin/env python3
"""Count Encore-owned files not yet handled in the optimization work pass.

Fast-skip previously maintained sources with a specific historical proof, but
never confuse code triage with host or console performance validation.
"""
import json
import subprocess
from collections import Counter
from pathlib import Path
import re

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
handled={e["path"] for e in entries}
assert len(entries)==len(handled),"duplicate optimization owner"
assert handled<=owners,sorted(handled-owners)
allowed={"code_changed_in_batch","reviewed_without_new_code_edit",
         "historical_host_contract_reviewed","previously_integrated_source_change"}
assert all(e["disposition"] in allowed and e["evidence"] for e in entries)
audit=(ROOT/"docs/EDEN_CORE_AUDIT_DEPENDENCIES.md").read_text()
rows=audit.split("<!-- AUDIT_ROWS_START -->",1)[1].split("<!-- AUDIT_ROWS_END -->",1)[0]
by_id={}
for line in rows.splitlines():
    if not re.match(r"^\|\s*[A-Z]\d{2,3}\s*\|",line):
        continue
    cells=[v.strip() for v in line.strip().strip("|").split("|")]
    assert len(cells)==9
    assert cells[0] not in by_id
    by_id[cells[0]]=dict(path=cells[3],status=cells[5],evidence=cells[6])
for e in entries:
    if e["disposition"] not in {"historical_host_contract_reviewed",
                               "previously_integrated_source_change"}:
        continue
    cid=e["contract_id"]
    assert cid in by_id,("historical contract missing",cid)
    row=by_id[cid]
    assert row["path"]==e["path"]
    assert row["status"]==e["prior_status"]
    assert row["evidence"]==e["proof_ref"]
    assert row["status"]==("HOST" if e["disposition"]=="historical_host_contract_reviewed"
                          else "SOURCE")
    assert e["path"].startswith("vendor/encore-active/")
    # A skipped *first code review* still leaves independent test/console debt.
    assert "PS5" not in e.get("claimed_performance","")
status=Counter(e["disposition"] for e in entries)
assert len(owners)==STATE["owned_code_count_at_snapshot"],("source inventory changed",len(owners),STATE["owned_code_count_at_snapshot"])
assert len(owners)==len(handled)+len(owners-handled)
print("EDEN_OPTIMIZATION_REVIEW_BACKLOG_PASS",
      "owned_code="+str(len(owners)),
      "handled="+str(len(handled)),
      "code_touched="+str(status["code_changed_in_batch"]),
      "source_reviewed="+str(status["reviewed_without_new_code_edit"]),
      "prior_host="+str(status["historical_host_contract_reviewed"]),
      "prior_source="+str(status["previously_integrated_source_change"]),
      "remaining_to_triage="+str(len(owners-handled)),
      "new_code_fixes_required=UNKNOWN native_console_validation=SEPARATE")
