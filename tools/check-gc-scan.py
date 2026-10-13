#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R439 source contract and behavioral model; no PS5 required."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
port = (root / "tools/prepare-vulkan-port.py").read_text()
perf = (root / "headless/performance.h").read_text()
main = (root / "headless/main.cpp").read_text()
active = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
start = active.index("void TextureCache<P>::RunGarbageCollector() {")
end = active.index("\ntemplate <class P>", start)
gc = active[start:end]
assert "gc_count_visits{false}" in perf
assert 'entry == "gc_scan=upstream"' in main
assert "gc_count_visits.store(false" in main
for item in ("size_t num_scanned = 0", "max_scanned = 8192",
             "num_iterations == 0 || num_scanned >= max_scanned",
             "++total_scanned;", "++skipped;", "++evicted;",
             "num_scanned = 0; // independent scan allowance for the aggressive pass",
             "EDEN_VULKAN_GC_SCAN"):
    assert item in gc, item
assert gc.count("gc_count_visits.load(std::memory_order_relaxed)") == 2
assert "Pinned GC scan anchor changed" in port and "gc_ending" in port
def model(items, budget=10, limit=8192, old=False):
    visits = evictions = 0
    for eligible in items:
        if budget == 0 or visits == limit:
            break
        visits += 1
        if old:
            budget -= 1
        if not eligible:
            continue
        if not old:
            budget -= 1
        evictions += 1
    return visits, evictions
items = [False] * 200 + [True] * 15
assert model(items) == (210, 10)
assert model(items, old=True) == (10, 0)
assert model([False] * 10000) == (8192, 0)
assert model([True] * 100) == (10, 10)
print("R439 GC scan contract PASS")
