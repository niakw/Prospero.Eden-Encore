# Dynarmic multi-page block-range invalidation — 22 October 2026

## Observed correctness / throughput issue

A guest A64/A32 block may span multiple 4 KiB guest-code pages. The
maintained `BlockRangeInformation::AddRange` indexed such a block in
each page bucket. The old `InvalidateRanges` only removed an invalidated
entry from buckets directly visited by the write range.

When the write intersected just the first page of a multi-page block, other
buckets retained a stale location descriptor. A later recompile of the same
guest location covering a *shorter* range could then be spuriously evicted by
a write to the old trailing page. The stale page entries could also accumulate.

## Selected native fix

- On encountering a matching entry, collect the original compiled block's
  full page span. Every invalidated location is removed from those buckets.
- Sort and deduplicate only the touched owner page indices; **do not scan**
  every JIT index bucket or erase live unrelated blocks.
- Retire empty buckets and preserve the existing per-page 4 KiB index.
- Keep A64/A32 default per-core compilation, sparse JIT allocation and
  RX/RW alias publication policy unchanged.
- Pin the maintained Dynarmic source blob to the updated code.

## Evidence / qualification

`tools/check-native-jit-block-range-rebase-host.py` compiles the actual
maintained C++ method bodies at `-O0` and `-O2` under UBSan. It covers a
two-page block, invalidation of the first page, another live block on the
same last page, shorter recompilation of the same location, and overlapping
later ranges. The prior implementation fails this source-selected witness;
the corrected version passes both optimization levels.

The fast gate has passed, including full regenerated Vulkan parity.
Separate source preflight, native build and CodeQL checks qualify the exact
HEAD independently.

Archived FC27 phase telemetry shows that in an early detailed window,
the three active guest JIT workers spent approximately 10.20 s in emit
out of 12.43 s cumulative compile time (82%, aggregated across workers).
This directs subsequent performance work toward emitter hot paths; it does
not prove frame-level causality or quantify any gain from this fix.

No console stability or stutter reduction is claimed until hardware evidence.
