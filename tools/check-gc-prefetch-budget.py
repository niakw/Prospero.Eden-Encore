#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R442: GC staging budget must mirror the actual eviction budget."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
included = (root / "headless/vulkan_gc_downloads.inc").read_text()
active = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
port = (root / "tools/prepare-vulkan-port.py").read_text()
gc_begin = active.index("void TextureCache<P>::RunGarbageCollector() {")
gc_end = active.index("\ntemplate <class P>", gc_begin)
gc = active[gc_begin:gc_end]
# The include is the canonical source used by the pinned port generator.
assert "(port / 'vulkan_gc_downloads.inc').read_text()" in port
for statement in (
    "size_t remaining = num_iterations;",
    "size_t scanned = 0;",
    "const bool count_visits = ::Eden::Performance::gc_count_visits.load(std::memory_order_relaxed);",
    "if (remaining == 0 || scanned >= max_scanned) return true;",
    "if (count_visits) --remaining;",
    "if (!count_visits) --remaining;",
):
    assert statement in included and statement in gc, statement
assert gc.count("if (remaining == 0 || scanned >= max_scanned) return true;") == 1
assert gc.count("num_scanned >= max_scanned") == 1

def visit(candidates, budget=10, cap=8192, old=False):
    """Model the shared scan decisions; statuses 0=decoding, 1=costly, 2=evictable."""
    scanned = removed = 0
    for status in candidates:
        if budget == 0 or scanned >= cap:
            break
        scanned += 1
        if old:
            budget -= 1
        if status != 2:
            continue
        if not old:
            budget -= 1
        removed += 1
    return scanned, removed

# Previously the prefetch loop spent its 10 slots on decoding textures.
items = [0] * 120 + [1] * 60 + [2] * 24
assert visit(items) == (190, 10)
assert visit(items, old=True) == (10, 0)
# The 8192 cap bounds the scan even under memory pressure.
assert visit([0] * 20000) == (8192, 0)
for stop in (10, 20, 40):
    for skipped in (0, 1, 99, 8192):
        items = [0, 1] * (skipped // 2) + ([0] if skipped % 2 else []) + [2] * 60
        visits, deleted = visit(items, budget=stop)
        assert visits <= 8192 and deleted <= stop
        if skipped < 8192:
            assert deleted == stop
print("R442: prefetch/GC scan budget parity source + behavioral model PASS")
