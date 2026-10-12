# R396 — FC27 R394 full-match PS5 evidence: visual stutter at nominal 30 FPS, late game freeze

**Do not require another user test to complete source review.** This report supersedes the earlier partial-trace inference. The user reports severe in-game stuttering for ~75% of play *despite a mostly-30-FPS counter*, with texture/grass pixelation and intermittent HUD/jersey faults, plus an application/game freeze at the end.

## Immutable provenance

Native PS5 13.60 / FC27 `0100C49025D3E000` / source SHA `4c84f90cf31804ee8e1301798e7f9be8047d69ad`, seen in both boot trace and heap log. Vulkan game output 1440p, game resolution 1x, bilinear, FXAA, 59.94-Hz native display.

User snapshots `heap(20261012-212056).log` (114 windows) and `heap(20261012-213230).log` (237 windows) are the **same session continued**, not independent A/B runs. Do not add their totals. Latest full heap: 237 5-second windows covering 1189.746s, 34,453 presented frames, 28.957 *counted* FPS overall. Boot trace returns to launcher at +1235831ms (~20m36s after process start). `stderr(20261012-213235).log` confirms orderly game shutdown, not a trapped native signal.

## Two distinct failures, not one "low FPS" bucket

**A. Most reported in-game stutter occurs while nominal FPS is ~30.** In the complete sample, 161/237 five-second windows are >=29.9 FPS; among these, measured late50 is zero for 159 windows and one for two windows. The present cadence counters have overwhelmingly v2 (two 60-Hz vblanks) with no conspicuous >50ms intervals. Therefore presentation callback statistics CANNOT disprove the user's visual jerks, repeated-content images, scene stepping, or texture flickering. The existing FPS HUD is not a content/simulation-freshness measurement.

**B. Occasional severe sub-30 windows correlate with guest GPU buffer-cache contention.** 750 output intervals exceed 50ms in 237 windows; 2,097 exceed 38ms. Under <25 FPS (17 windows) the mean buffer-cache lock wait is 138.64ms per 5s vs 13.74ms in >=29.9 FPS windows. Mean buffer contention 8,555 vs 1,218 per 5s. Mean texture-lock wait **is also nonzero**, 17.8ms vs 29.1ms. These are window associations; don't attribute all visual stutter or corrupted textures to a buffer mutex.

### Near exit / apparent freeze

The last three five-second windows are ~30 FPS, `worst_ms ~=34ms`, zero reported buffer-cache contention, and the Vulkan GPU owner still schedules ~40,000 draws per five seconds. Guest IPC and CPU-write calls continue (roughly 7,800 and 54,000 respectively per 5s). A visually frozen game with an active rendering loop therefore **is not the same as a dead GPU/Vulkan worker**. The last two CPU sampled guest PCs for cores 1/2 repeat, but this alone is not sufficient to assign a root-cause deadlock.

At the end of stderr: pad `options_edges=3, create_edges=1`; the PS5 guest emulation exits via user shortcut, then `Completed kernel.ShutdownCores`, `Completed gpu_core.reset`, `Completed kernel.Shutdown` and launcher starts again. No `EDEN_CRASH` handler dump. Classify it as a **guest/game logic freeze or visual hang** until independently proven otherwise, not native process crash. Do not claim native crash fixes solely from these logs.

### Texture correctness remains an open first-class issue

The Vulkan texture cache logs stable `usage=4,380,950,528`, `expected=4,724,464,026`, `critical=5,583,457,485`, `keep_dirty=1`, `memory_short=0` near end. These numbers rule out a pressure-triggered dirty GC eviction *in those windows*, **not** stale textures, mismatched aliasing, missing HUD, broken format reinterpretation, shader defects, DMA invalidation errors, or pixelation. Recorded `EDEN_GPU_DRAW_DROP` counters remain zero, but that does not establish correct image data.

The emulator still chooses 1x game resolution, 1440p output, FXAA, bilinear. Do not explain away moving-pitch pixelation as simply user settings without a valid shader/texture and motion-state examination.

### DNS audit workload

`network-accepted(2).log` is **append-only across sessions** and contains 6,960 guest denied events across three separated timestamp clusters. DO NOT attribute all of them to R394. The cluster aligned with this ~20-minute R394 run starts at epoch=1791839457 and ends at 1791840634; it contains **2,872 denied guest DNS events**, including 2,826 for `spring25.client.blazeredirector.ea.com` and 38 for `collector.errors.ea.com`. Average ~2.47 denied events/sec across the run, with isolated bursts up to 31/sec. Small relative to guest draw/IPC rates; audit load is not proven to account for gameplay stutter. Policy correctly returns `GetAddrInfoError::NODATA` for denied hosts; do NOT alter denylist or return success to EA/Nintendo. The network observer's per-denial formatting/mutex/file-write is diagnostic overhead and is unrelated to network correctness.

R396 reduces repeated same-second guest DNS *audit* events via atomic key and summary counters without modifying DNS policy. This is a bounded log overhead reduction, **not** a confirmed fix for visual stutter, textures, or the freeze. Validate with `tools/check-network-accepted-audit.py`, and run source CI.

## Real next engineering targets

1. **30-FPS visual jitter:** audit PS5 scanout source vs emulated frame content updates and emulator guest time progression, rather than pretending 30.000 FPS callback cadence means stable game simulation. Check Vulkan PresentManager/Swapchain staging and any duplicate/latest-frame semantic before changing pacing.
2. **Texture/HUD correctness:** inspect all write, alias scan/copy, descriptor invalidation, rescaled image and feedback-loop paths in active `vendor/encore-active/eden-vulkan` and pinned underlying texture-cache backports. Any correction must preserve view lifetime and GPU fences, not just lower accuracy.
3. **Low-FPS buffer conflicts:** shorten the *actual* paired buffer/texture critical section only for operations proven to require neither mutable cache. Never skip guest invalidation or remove locks from asynchronous descriptor uploads speculatively.
4. **End-of-match freeze:** isolate guest service/IPC semantic progress and game-frame updates while graphics still runs. The old R393 128-slot per-thread table hit overflow; R395 adds bounded 1024-slot/64-probe instrumentation, but it is diagnostics only. No native crash trace was produced by R394.
5. Do not ask the user to repeat the same 20-minute session solely to establish known correlations. Only present another PS5 package as a meaningful integrated fix after CI, with clear build SHA.

**Do not claim R396 resolves the game yet.** Source and CI changes are separate from physical hardware qualification.
