# R323 — 1440p FC27 R322 FTP forensic results; PS5 descriptor-ring frame preflight

Branch `dev/ps5-sparse-jit` after R322 native #38154183680 **SUCCESS**. Pinned Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`. Evidence from authorized read-only FTP of the **user's actual FC27 R322 1440p run**, `/data/prosperoeden/logs/heap.log`, `eden_log.txt`, `stderr.log`, `network-accepted.log` collected October 11.

## Correct interpretation of cumulative phase counters

116 consecutive five-second windows at 2560×1440, about 580s. FPS median 30.0; 420 presented frames >50ms, 51 >100ms, 17 >200ms, 2 >500ms; maximum 567.710ms. 231171 `cache_contended` events, 5911.268ms **cumulative across concurrent guest threads** of cache lock blocked time. These metrics use detailed logging and the counts are not the same without instrumentation. Frames #16054 and #16139 fall below 20 FPS with 14,308 and 9,826 cache conflicts, low JIT time (36.866ms and 71.754ms per 5s), plus GPU queue full 66.628ms / 93.493ms.

**Crucial:** `EDEN_GPU_CACHE_PHASE samples` and `total_ns` are **cumulative since launch**, NOT per-five-second figures. Only `max_ns` resets each window. Subtract successive adjacent windows. R322 first-to-last deltas for 115 windows: GPU paired locks 3.272s sampled; pipeline Configure 2.785s sampled; FillImageViews 0.440s sampled; texture_cpu_refresh only **0.016s** sampled (169 refresh calls); texture_alias_scan 0.008s sampled (221802 calls); texture_alias_copy 0.006s sampled (1004 calls). Per-call sampled maxima: fill views 3.470ms, CPU refresh 1.228ms, alias scan 0.020ms, alias copies 0.016ms. These sums are measured on 1/16 draws, not total physical GPU time. It is **incorrect** to sum each cumulative `total_ns` line across windows.

**Diagnosis:** R320/R321 alias work is not the primary cause of FC27 frame pacing. CPU refresh sometimes costs ~1ms but cannot by itself explain persistent 30-FPS perceived stuttering and severe cache contention. The remainder of ConfigureImpl, dynamic state, descriptor paths, producer/consumer scheduling, and guest CPU performance still need qualification.

The 1440p log reports high GPU accuracy, not memory shortage (`memory_short=0`, last 4.076GiB texture usage vs expected 4.40GiB budget), no GPU unmapped counters, and no game crash this run. On the guest side there were **96 Fermi2D warnings** about non-unit source depth during approximately 2.2s around guest time 103-105s; upstream Fermi2D still runs the blit afterwards. They may relate to image problems but cannot explain ten minutes of stuttering alone. No unsafe 3D->2D replacement implemented.

The native accepted/blocked network log is cumulative across earlier runs. In the latest 600s only **1726** events occurred, including 1691 denied DNS requests to `spring25.client.blazeredirector.ea.com`. They prove repetitive guest retries, not that DNS caused graphics stalls. Keep network policy unchanged.

## New bounded R323 fix

Pinned Vulkan `DescriptorBufferRing::Allocate` calls `scheduler.Wait(frame_ticks[frame_index])` when `frame_reused` is set, and also may `scheduler.Finish()` on capacity exhaustion. `Allocate` is called inside `GraphicsPipeline::ConfigureDraw`, while `PrepareDraw` holds **both** buffer and texture cache mutexes. This is a real potential cause of guest CPU lock stalls independent of shader compilation or texture aliases.

R323 adds **PS5-only** `PreflightFrameReuse` to Vulkan DescriptorBufferRing: for an active ring and pending recycled-frame wait, it performs the **same exact scheduler fence wait** and clears `frame_reused` before the caller's cache lock. It is invoked only when the selected graphics pipeline can use descriptor buffers. After a wait, guest-memory invalidations are re-flushed before acquiring the cache pair. No GPU worker flush is added, no descriptor allocation order or generation changed, and the original `Allocate` wait/capacity fallback and `scheduler.Finish` remain fully intact. All non-PS5 code guarded.

This **does not remove the GPU wait**: it relocates the wait so other guest cores are less likely to queue behind the paired graphics locks. The frequency of such waits in FC27 is **not measured**, so performance benefits are not asserted. The R322 user report confirms persistent stutter at 1440p. Only a later on-console match can validate.

## Regression

`tools/check-ps5-descriptor-ring-preflight.py` SHA-checks pinned Eden Vulkan ring/rasterizer source, extracts real production source adapters, verifies the wait occurs before both cache locks and original capacity/Finish fallback survives, compiles the native method in a C++20 scheduler mock with no-ring, no-pending-fence, pending-fence and subsequent frame reuse, and verifies upstream builds remain unchanged. Wired to host/core and native-build gates. Source checks are NOT proof of real FPS gain.

## Validation CI / qualification native

Le précontrôle de source [#38156955114](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38156955114) est **SUCCESS**, incluant le scénario C++ épinglé du déplacement d’attente Vulkan. Le build PS5 All-On est explicitement lancé par le présent commit documentaire. La conformité native reste à vérifier indépendamment du précontrôle, et l’amélioration en FPS ou en régularité n’est pas démontrée.

## R323 native link repair — keep the adjusted descriptor source in the final build

Native All-On [#38157123481](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38157123481) failed at the final ELF link, **not** because the new fence wait has invalid semantics: `undefined symbol: Vulkan::DescriptorBufferRing::PreflightFrameReuse`. The generator wrote the R323 implementation into intermediate `vulkan_descriptor_buffer.cpp`, but the later Vulkan wait-cost adapter re-read *pristine* upstream source and emitted the actual compiled `vk_descriptor_buffer_cost.cpp`, accidentally dropping the new method. The same script already preserves the intermediate adapted swapchain correctly.

The repair makes the descriptor-cost adapter consume `vulkan_descriptor_buffer.cpp`, preserving R323, and updates the expected wait/fence instrumentation sites from 2 to 3. A new pinned-source check recreates the **final** instrumented translation unit and asserts R323's method plus both original and preflight frame waits are present. Only the final-compilation integration is changed; the fence semantics and locking implementation remain identical. R323 must pass source CI and a *new* native All-On link before any on-console testing.
