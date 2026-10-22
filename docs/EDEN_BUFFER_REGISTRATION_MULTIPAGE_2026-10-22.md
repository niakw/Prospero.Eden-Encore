# Buffer ownership: multi-page CPU invalidation (22 October 2026)

## Root cause and impact

The native `BufferCache::IsRegionRegistered` walked caching pages only until
it found a *non-overlapping* buffer occupying the first partial page. Instead
of checking subsequent pages, it set `page` to the end of the whole query.

Example: a small buffer registered in `[0x1000,0x1400)` and another buffer
in `[0x2000,0x2800)`. A guest write to `[0x1800,0x2800)` overlaps the
second buffer, but the old implementation returned false. This can suppress
buffer dirty-state publication and leave a stale GPU buffer until later work.

The test uses the actual method body extracted from the native maintained
buffer cache, with optimized and nonoptimized host builds under UBSan.
The previous loop fails the multi-page overlap witness; the corrected loop
passes. Zero-sized queries are explicitly rejected as non-overlapping.

## Selected patch and validation

- `vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h`
  carries the native-specific fix selected by the PS5 CMake profile.
- The 83 shipping backport sources and their exact hash-locked manifest remain
  unchanged; the source replay still installs identical pinned inputs.
- The independent native R437 reconstruction oracles apply the narrow fix
  after the original backport and DMA-width protections.
- `tools/check-ps5-buffer-region-multipage-host.py` covers a partially
  overlapping first page, later owned pages, unowned gaps, direct overlap
  and a zero-length guest range.
- The fast host gate confirms the regression at `-O0` and `-O2`, plus
  pinned 41-unit Vulkan regeneration and ordinary JIT/GPU source contracts.

## Qualification boundary

This patch fixes an actual false-negative buffer ownership query. It does
not prove FC27's HUD, jersey textures or frame pacing are corrected. Console
testing should only happen after the remaining independently measured JIT
and cache-wait bottlenecks have an actionable fix and a green release build.
Do not enable the experimental deferred guest-write bridge or unsafe JIT
sharing as a workaround without separate quiescence and ordering evidence.
