#!/usr/bin/env python3
"""Network-free completed vs blocked vs offline query count regression."""
import importlib.util
from pathlib import Path
sp=importlib.util.spec_from_file_location("eden_glyph_accurate_counts",
   Path(__file__).with_name("ps-glyph-run-metrics.py"))
assert sp and sp.loader
m=importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)
results=[
  {"schema":1,"provider":"github",
   "games":[{"title_id":"01007EF00011E000","discovery_status":"searched_links_found"},
            {"title_id":"0100AAA000111000","discovery_status":"searched_no_matching_links"}],
   "requests_completed":2,"requests_attempted":2,"errors":[],"source_leads":3},
  {"schema":1,"provider":"curl_duckduckgo",
   "games":[],"requests_completed":0,"requests_attempted":1,
   "errors":[{"reason":"HTTP 429"}],"source_leads":0},
  {"schema":1,"provider":"none",
   "games":[{"title_id":"0100AAA000111000",
             "discovery_status":"query_prepared_not_executed"}],
   "requests_completed":0,"requests_attempted":0,
   "errors":[],"source_leads":0}
]
report=m.summarize(results,"example-run")
assert report["total_attempts"]==3 and report["total_completed"]==2
assert report["total_blocked_or_failed"]==1 and report["source_leads_observed"]==3
assert report["providers"][1]["first_block_reason"]=="HTTP 429"
try:
    m.summarize([dict(results[0],requests_completed=3)],"bad")
except ValueError:pass
else:raise AssertionError("fabricated three successful searches from two game records")
print("PASS: counts include only actual completed searches and explicit blocks, never prepared links")
