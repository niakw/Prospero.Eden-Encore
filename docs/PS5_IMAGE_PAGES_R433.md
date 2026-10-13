# R433 — PS5 Vulkan texture-cache read lock avoidance

Ported selectively from [ProsperoEden d7f2764](https://github.com/blackbearreloaded/ProsperoEden/commit/d7f2764f8ecf8bdbd979eece2b402621edceee2f) without merging its launcher, CPU affinity changes, frame-clock scaling, or asynchronous ASTC image policy.

## Problem

A guest CPU memory read asks RasterizerVulkan::GetFlushArea whether a GPU-modified texture requires download. Prior Encore always acquires the texture cache mutex—even when no texture has EVER been registered at that guest physical memory range. The GPU often holds this mutex across draws, creating contention at steady 30 FPS.

## Bounded approach

- A 512 KiB, initially zeroed, process-global atomic bitmap describes the full 16 GiB device-address range at 4 KiB granularity.
- TextureCache::RegisterImage marks a dense image's CPU range or EACH sparse segment before adding the slot-map entry; it NEVER clears marks. Registered or formerly registered pages always use the original mutex path.
- GetFlushArea fast-returns the unchanged preemptive download-area fallback only for valid ranges with no marked pages.
- Out-of-space, overflow, or queries larger than 256 KiB use the original lock. Long-range queries cannot scan unbounded bitmap words on a guest critical path.
- Producer writes release and consumer reads acquire; only the bitmap is lock free. The original cache registration, invalidation and readback behavior and lock ordering are unchanged.
- Pinned Eden archives remain untouched. The active Vulkan fork and tools/prepare-vulkan-port.py are modified together, with a source-replay oracle in the core preflight.
- R433 host C++ tests cover page/word boundaries, large spans, sparse ranges and parallel marking under ASan/UBSan.

## Caveats and verification

This is a **lock contention hypothesis**, not a measured FPS gain. The bitset is deliberately monotonic and may become less selective after many game sessions, but never becomes optimistic because of eviction. In concurrent registration, marking precedes slot-map insertion, but a CPU read racing a registration can still linearize before the mark, as with an unsynchronized guest read; rendering fidelity and HUD correctness must be verified on hardware. Until R433 is built, the R432 all-on package is the last native-qualified image.

No changes to DualSense/gameplay mapping, PS5 firmware affinity, image resolution, shader compilation, texture conversion, or guest frame timing.
