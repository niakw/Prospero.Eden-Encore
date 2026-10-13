# Eden Encore R441 — Hot path audit and source-proven external paths

Source audited: dev/ps5-sparse-jit, after R440. Source-only, no PS5 native build.

## Repeated-frame and shader wait

- `vk_pipeline_cache_cost.cpp::CurrentGraphicsPipelineSlowPath` creates first-use graphics pipelines, and the PS5 `BuiltPipeline` returns an unbuilt pipeline rather than drop a draw.
- `vk_graphics_pipeline_cost.cpp::ConfigureDraw` inserts an ordered `scheduler.Record` callback waiting on `build_condvar` for the pipeline to become ready.
- `vulkan_scheduler.cpp::WorkerThread` holds `execution_mutex` while executing that callback. A cold compilation can **block the Vulkan worker** while the separate shader-building worker runs. This is analogous to Pereira's #676, but not Wine's PE stream gate; bypassing this ordering could drop HUD draws or race descriptor resources.
- `vulkan_rasterizer.cpp::PrepareDraw` takes the **buffer+texture cache lock pair** around pipeline configuration/descriptor setup. Existing source-phase probes cover pair waits, texture alias scans/copies, and descriptor work; no authoritative same-frame proof that these cause FC27's freeze.
- `vulkan_present_manager.cpp::Present` can progress in a thread independently of the game's simulation. A 30 Hz present counter may continue during a guest freeze. Avoid using presents as the simulation-progress clock for Swordpdf's frame generation.

## Already ported: do not duplicate

- Official Mihawk PS5_Mesa 120 Hz offer/configuration validation entered Encore in **R400**, despite R438's stale version comparison.
- PS5 input `headless/pad.cpp` already calls `scePadRead` with a full buffer and consumes each returned sample; drakmor's gamepad batching research confirms this design.
- Pereira's shader disk cache credentials fix entered R414, so do not reapply.
- R439 GC has an independent 8192-visit traversal bound and historical 10/20/40 eviction budgets with rollback. R441 teaches the existing offline log analyser to read `EDEN_VULKAN_GC_SCAN` without incorrectly aligning sparse samples to unrelated five-second telemetry.
- R440 ports Pereira's unpresented-swapchain takeover (host-model-tested upstream). The author did not establish PS5 native qualification for **that exact patch**, and neither have we.

## Rechecked relevant sources

- [mpereiraesaa/prospero-win](https://github.com/mpereiraesaa/prospero-win): 0881/0882 CPU affinity/fairness, PR #676 Vulkan compilations outside global Wine stream lock, 0879 GUI wake-state bug.
- [mpereiraesaa/PS5_Mesa 9d3cd417](https://github.com/mpereiraesaa/PS5_Mesa/commit/9d3cd417ff488bd1a7cc68c1f1c8e1df409c2a11): off-size swapchains and refused VideoOut allocation cleanup validated through its author host model after native Wine evidence. Needs ownership adaptation: Encore's WSI always registers 3840x2160, unlike Pereira's scalable WSI.
- [Swordpdf/ps5-framegen](https://github.com/Swordpdf/ps5-framegen): reusable Vulkan optical-flow interpolation proven in PS5SX2 (ps5vk) and RPCS3-PS5 (RADV). Pacer must use guest/source ticks, not repeated presents, to avoid self-feeding; it cannot unfreeze game simulation or repair corrupt render targets.
- [drakmor/ps5-hwinfo](https://github.com/drakmor/ps5-hwinfo): CPU/GPU clock and logical-load diagnosis; payload APIs may not work from an ordinary native title.
- [EchoStretch/kstuff-lite](https://github.com/EchoStretch/kstuff-lite), [soniciso1/ps5-linux-archive](https://github.com/soniciso1/ps5-linux-archive), [ntfargo/Relapse-Exploit](https://github.com/ntfargo/Relapse-Exploit): loader/firmware/ABI evidence rather than drop-in frame timing patches.
- [ArkSama/PS5_RPCS3](https://github.com/ArkSama/PS5_RPCS3): PS3 port reference with distinct GPL license/distribution boundary; [Unlock PS5 Pro memory](https://github.com/ArkSama/Unlock-ps5-pro-memory) benefits Pro models, not Encore's base PS5.
- External Mesa [RADV docs](https://docs.mesa3d.org/drivers/radv.html) and [26.2 release notes](https://docs.mesa3d.org/relnotes/26.2.0.html): userspace SPIR-V -> NIR -> ACO, separately from PS5 native GPU winsys; cherry-pick specific proven correctness work instead of blindly rebasing a diverged Mesa fork.

## Practical order

1. Keep source/CI checks after porting, do not require another user hardware test *before* implementation.
2. Diagnose worker shader waits vs stalled guest CPU progress; preserve queued GPU draw correctness.
3. Improve texture descriptor residency/HUD alias freshness, not stale readback shortcuts.
4. Port author's image-size WSI only as one coherent ownership change.
5. Import Swordpdf framegen full sources, shaders, licenses and native presentation integration as a separate optional feature once guest-tick pacing can be trusted.
6. Bundle console testing across changes. Never equate a green host contract with verified PS5 FPS/fidelity.

## R442 — Align GPU-written texture prefetch with R439 collector (2026-10-13)

Confirmed mismatch: R439's `Cleanup` counts actual eligible evictions while `headless/vulkan_gc_downloads.inc::PrefetchDownloads` still decremented its 10/20/40 batch lookahead allowance before checking IsDecoding/CostlyLoad. Under LRU-skew, the collector could evict dirty images that were not prefetched, forcing individual GPU Finish() waits. R442 now mirrors the collector's **8192 bounded visits**, skip semantics and `gc_scan=upstream` visit-count rollback in both the generator include and checked-in active source. It does not expand the maximum of 40 prefetched downloads or the 32 MiB byte budget, change guest GPU memory ownership, or discard draws. Adds a host contract/model `tools/check-gc-prefetch-budget.py` and R439 cross-check update. Source-only; no FC27 performance claim before a native run.

## R444 — Prioritize gameplay shaders until cold compilation drains

Source inspection confirmed the secondary `VkPipelineOptimize` worker could begin `MakePipeline` as soon as a fixed 48 ms delay expired, even when `pending_first_use_graphics_builds` remained nonzero. With only 13 logical CPUs allowed, concurrent compilation can contend for both CPU and RADV cache operations exactly as first-use draws are stalled. The optional optimized pipeline is **not needed for correctness** because its fast-first pipeline is already valid. R444 holds only the background optimizer while the first-use counter is nonzero; it checks per-pipeline cancellation with a short 2 ms sleep. The existing `OptimizeState` mutex ensures title teardown aborts a waiting worker even if a first-use build remains stuck, without holding any guest/GPU locks. Source generator and checked-in Vulkan copy are identical. The host C++ gate now covers a 100 ms backlog that formerly let optimizing begin at 48 ms, cancellation during a permanent backlog, and immediate idle path. No claim of a measured FC27 FPS gain yet.
