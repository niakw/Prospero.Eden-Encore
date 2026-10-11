# R338 — audit PS5_Vulkan (Mihawk) vs Eden Encore native PS5 RADV

Date: 2026-10-12. Repo source: <https://github.com/mihawk-99/PS5_Vulkan>, `<main>`; related fork: <https://github.com/mihawk-99/PS5_Mesa>. This is a dependency and causality audit, **not a claim to fix FC27**.

## A. Important correction to the root-cause process

Eden Encore **already links Mihawk's Mesa RADV port**, not Mihawk's older standalone `ps5vk` Vulkan 1.1 driver. `headless/CMakeLists.txt` selects `EDEN_VULKAN_DRIVER=RADV`, `tools/build-package.sh` sets it, and `tools/check-radv-native.py` verifies the final `libvulkan_radeon.ps5.a` and absence of `libps5vk.a`. It also asserts instance entrypoints/allocator ownership. The dependency build validates pin identities, builds the **release** Mesa archive, and applies an explicit WSI VideoOut lifetime patch. Consequently, migrating from ps5vk to RADV is **not** the missing step.

Exact `tools/deps.json` pins at this review:

- `PS5_Vulkan`: `3f3ee69607013b345d2baa6d6a37c86745649a08` (the linked repository's current main is 18 commits ahead; changes include revised VideoOut and optional GPU broker/Zink infrastructure).
- `PS5_Mesa`: `0b2d6d1a61d9bbf89cf8beb88a696144f67c61f8`. Current main is **diverged** (GitHub comparison reported 110 ahead / 103 behind, merge base `9f0a761020bca92f2b07156a0621e5360cb8eca5`), so blindly substituting latest main is unsafe; our WSI source patch relies on exact anchors and our SDK fork is version-matched.
- Payload SDK fork: `95c08f27386fc698f6bbe21dde3030140a41d10b`.
- At the pinned PS5_Vulkan revision, `tools/build-radv.sh` points exactly at pinned Mesa `0b2d6d1a...`, so Eden's manifest is internally consistent.

## B. Driver capabilities actually present in our pinned Mesa

Verified by fetching *pinned* source (not just current README):

- `src/amd/vulkan/winsys/ps5/radv_ps5_platform.c` already uses `clflushopt`, a background `radv_ps5_kick_body` thread, and separate submit stage timings (`radv_ps5_submit_times`). Mihawk's README records an older ~0.3 ms per-summission suspend cost reduced by these improvements. **No new backport is needed** for these two paths.
- `src/util/mesa_cache_db.c` already implements `mesa_cache_db_open_exclusive()`. The pin also has `radv_threaded_layer.c` gated by `RADV_THREADED_RECORDING`; Mihawk explicitly leaves optional threaded recording **off** until a game proves faster. Do not force the flag to chase FC27 stutter.
- Eden already sets the writable `MESA_SHADER_CACHE_DIR` and a disk-aware maximum. The user's full cache purge not changing FC27's persistent hiccups argues against a *sole* stale shader cache root cause; an empty-cache compile cost may still occur early.
- `dev_vulkan.h` enables needed compute barriers by default, after earlier LOD/streaming visibility bugs. It disables arbitrary custom border color by default due to a still-open game GPU fault. This workaround can sacrifice exact sampling of a small set of border colors but is not a demonstrated reason for all grass/HUD corruption.

## C. What Mihawk reports missing (and which claims apply to us)

- **PS5 Mesa RADV**, not ps5vk: true concurrent compute/transfer queues are not available yet; those families are served serially on the graphics ring. This makes guest compute/draw interleaving and host GPU queue pressure worth profiling, but does **not** prove FC27 stutters are caused by hardware underuse or incomplete queues.
- Radeon output uses PS5 VideoOut and a vblank-based FIFO presentation path; the pinned driver version predates the 2026-10-04 per-VideoOut-size mode offering and 2026-10-10 119.88Hz capability reporting refinements. Eden's own WSI adapter also modifies 120Hz fallback detection and VideoOut cleanup. The user's baseline was 1440p application output, 1× internal rendering and PS5 60Hz; do not assume high-refresh improvements automatically apply to that baseline. Test consistency of versioned WSI before any upgrade.
- Mihawk demonstrates 4K60 on *a different tested game* in his experimental ProsperoEden fork and about 19% GPU utilization. It proves useful PS5 RADV headroom exists, **not** that FC27 can reach the same with our guest workload.
- Mihawk's R37 mapped-target flush, R42 parallel blit and R43 hitch recorder numbers are for **the older ps5vk driver** and its vkQuake port. They are invaluable profiling examples, but must not be blindly applied to our Mesa RADV implementation. In particular, bulk cache flush changes need readback/golden-image checks; avoid worsening user-visible HUD/grass correctness.
- Mihawk has real-pixel output comparison tests (Vulkan sample output vs PC reference, texture/mip canaries) whereas Eden's current FPS counters are derived from `RendererVulkan::Composite`'s `OnFrameDisplayed()` callback, which runs **before successful GPU presentation**. Therefore its 30FPS reading during the FC27 menu freeze never proved unique new images are reaching the TV.

## D. Priority order for the unresolved FC27 bugs

1. **Before a risky driver upgrade:** derive a host-side comparison of pinned versus candidate PS5_Mesa source for VideoOut flip/fence sequencing and queue pacing; preserve all native lifetime adapters. Add 5-second-aggregate counters for *completed VideoOut flips* vs guest composition callbacks only if needed, never per-frame logs in the hot path. Verify actual content advancement separately from 30FPS counters.
2. Audit the guest rasterizer's accelerated framebuffer validity, pitch, tiled image view reuse, compute/fragment synchronization and texture invalidation around FC27's moving grass and transient HUD. Treat the existing source-level compute barrier fixes as present, not missing.
3. Profile *actual* PS5 RADV submit flush/queue/wake times using Mihawk's existing `radv_ps5_submit_times` hook, rather than attributing every stall to Eden's producer queue. Compare games/window phases; find backpressure **cause**, not just correlate.
4. Separate the frozen controller menu from in-match GPU queue saturation. Physical DualSense X/Y sample counters added R332 still lack qualified on-hardware evidence; static mapping correctness does not prove FC27 accepts reassignment.
5. Prefer targeted backports with source/CTS/sample image regression checks over a direct merge of diverged 110/103-commit Mesa histories. Upstream RADV shader cache and optional thread recording are not missing, so neither cache wiping nor blindly enabling concurrency are accepted fixes.

`tools/check-ps5-mihawk-radv-contract.py` is a fast source-only assertion of the currently used architecture and links. It does **not** establish Vulkan CTS compliance, output frame identity or game fluidity.

## E. Actual RADV submit telemetry found in FC27 FTP stderr

The original Mihawk RADV driver's internal 10-second (approximate) log is already active: `radv/ps5 submissions: window count=... kwords=... claim_ms=... copy_ms=... flush_ms=... agc_ms=... suspend_ms=...`. Parsed `/tmp/eden-freeze-fc27-20261011/stderr.log` (37 sample lines, same PS5 FC27 freeze session) on the connected Mac, and measured:

| Field | Total across recorded windows |
| --- | ---: |
| `count` | 37,376 commands submitted |
| `claim_ms` | 87.0 ms |
| `copy_ms` | 116.1 ms |
| `flush_ms` | 70.3 ms |
| `agc_ms` | 646.1 ms |
| `suspend_ms` | 2,069.3 ms |

Mean `suspend_ms / count = 0.05536 ms` per submission (~55 µs). The maximum single sample window had 2,687 submissions and 114.6 ms accumulated suspend time. `suspend_ms` is measured in the **dedicated kick thread** (`radv_ps5_kick_body`); its total over the session is not an additive 2-second block on Eden's guest CPU thread. Since even accumulated CPU copy and flush cost is only hundreds of milliseconds across several minutes, the PS5 release build **already implements Mihawk's submission optimizations**; adding CLFLUSHOPT or another kick worker cannot eliminate FC27's severe persistent stutters. Do not confuse 37 RADV ~10s samples with 175 frame ~5s samples from a *different* recorded session.

The existing severe visible FC27 menu freeze still has continuing GPU/IPC and ~30 `Composite()` callbacks per second, but neither these RADV logs nor `EDEN_VULKAN_FRAME` prove completed VideoOut flips or a changed scene pixel hash. Next correctness evidence should separate guest image content -> Vulkan present -> VideoOut flip acknowledgement; distinguish physical vblank pacing from composition attempts. No per-draw trace or cache purge is indicated from these numbers.
