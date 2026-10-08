#!/usr/bin/env python3
"""Upgrade only the verified previous Encore HTTP patch on a prepared Eden cache.

Caller must have checked the original patch receipt's exact SHA-256.
No other source file, compiled cache, or dependency is touched.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: migrate-net-user-agent-cache.py EDEN_SOURCE")
source = Path(sys.argv[1]) / "src/common/net/net.cpp"
if not source.is_file():
    raise SystemExit(f"Pinned Eden net.cpp missing: {source}")
text = source.read_text()
for marker in (
    'request.headers.emplace("User-Agent", "Prospero.Eden-Encore/1");',
    'request.headers.emplace("Accept", "*/*");',
):
    if text.count(marker) != 1:
        raise SystemExit(f"Previous HTTP patch marker missing/duplicated: {marker}")
old = '            LOG_ERROR(Common, "GET to {}{} returned null", url, path);'
new = ('            LOG_ERROR(Common, "GET to {}{} returned null: {}", url, path,\n'
       '                      httplib::to_string(result.error()));')
if text.count(new) == 1 and old not in text:
    print("Cached HTTP diagnostics already migrated (receipt update may resume)")
elif text.count(old) == 1 and new not in text:
    source.write_text(text.replace(old, new, 1))
    print("Cached HTTP diagnostics upgraded in one source file")
else:
    raise SystemExit("Unexpected cached HTTP source: refuse to alter the pinned Eden tree")
