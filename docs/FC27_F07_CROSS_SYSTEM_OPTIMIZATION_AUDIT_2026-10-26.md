# Eden Encore — performance audit without repeating previous work (26 October 2026)

**Branch:** `dev/ps5-sparse-jit`. This is a cross-subsystem execution map, **not** a claim that every emulation source is FPS-optimized. F01–F06 passed host pre-console contracts; F07 remains **OPEN** until same-build console evidence. The 491-source inventory is historical; source-review coverage and measured runtime bottlenecks are different quantities.

| Area / production owner | Already integrated; do not duplicate | Unresolved evidence / next precise investigation |
| --- | --- | --- |
| A32/A64 JIT / `headless/experimental_performance.h`, native Dynarmic | Bounded physical admission, code-space checks, alias memo; sparse/shared dev-only | CPU instruction progress and per-core compile/invalidation time during >100 ms frame gaps; no unconditional sparse or cache enlargement |
| Shader first-use / `vk_pipeline_cache_cost.cpp` | Asynchronous Vulkan pipeline *build*, release cold-creation timing `graphics_pipeline_create` | Guest IR→SPIR-V preparation remains synchronous in `CreateGraphicsPipeline()`; correlate first-use bursts with waits rather than bypass ordered builds |
| Vulkan worker / `vk_graphics_pipeline_cost.cpp`, `vulkan_scheduler.cpp` | Completion always wakes waiters; speculative optimizer yields to first-use builds when enabled | `ConfigureDraw` queues a build-condition wait in scheduler worker; attribute time/impact before changing worker lock boundaries |
| Graphics pipeline transitions / `vk_graphics_pipeline.h` | **This audit:** PS5-only hot transition index on lists >=8; no changes to pointers, keys or draw order | Host O0/O2 regression required; no hardware frametime improvement claimed |
| Paired cache locks / `vulkan_rasterizer.cpp`, `vk_graphics_pipeline_cost.cpp` | Preflight descriptor reservations; per-draw scratch reuse; 16-entry sampler memo; empty-descriptor acquire shortcut | Buffer cache lock vs texture cache lock *owner* duration and GPU dispatch in same late windows, not just aggregated wait |
| Texture upload / `texture_cache.h`, `vk_texture_cache_cost.cpp` | TIC/TSC guards, null-view revival, alias/invalidation tests; F07 staging/contents/barrier timers | Which upload subphase holds the lock >50ms? Check async decode/unswizzle decisions and avoid any stale texture shortcut |
| HUD/2D correctness / blit scheduler, framebuffer/present | Raw `DrawTexture` blit invalidates cached Vulkan graphics state (source/host) | Must observe actual updated pixel contents vs unchanged host presents and long-lived black HUD panels; host correctness ≠ console |
| DMA / F04 GPU copy path | Conservative overlapping/contiguous remap+upload witnesses and transfer barriers | F04 host replay must remain green after instrumentation changes; compare HUD, jerseys, pitch, not just crash counts |
| NvDisp/HLE guest progress / Binder, BufferQueue, Host1x, KThread | F05 release wake and handoff host fixtures; worker ordered publication | Pair guest PC/thread progress, frame **content** and input response during stalled menus and half-time |
| Input / Pad→NPad→LIFO | F06 synthetic linked source replay and 250 Hz poll | Input-to-visible-frame latency remains unknown; do not alter user-approved mapping as a GPU optimization |
| VRAM/GC/native allocation | Bounded GC scan and budgets, staged safe release, 4× OOM failure logs | Diagnose memory pressure separately from 1440p 1× stutter; no unconditional larger texture/JIT cache |
| Production profile / release vs DEV | Quiet GPU and JIT counters, diagnostics toggle restored on launch; unsafe CPU/DMA/skip invalidation OFF | Make sure instrumentation doesn't change quiet gameplay; compare selected PS5 build only, never unbuilt experiments |
| Launcher OpenGL/cover pipeline | Separate UI source-review ledger and asynchronous artwork decode | Do **not** confuse launcher covers/filters/AA and game Vulkan/HUD performance |

## Closeout criteria and no-repeat rule

1. Identify a **selected active** production source, precise repeatable cost, and an isolated safe edit. Archive changed source symbol, commit and host regression.
2. Source reviews alone never count as completed performance changes; a green host gate is not a matched PS5 improvement.
3. CI fast gate + full preflight + compiled PS5 package must pass **for the same SHA** before asking for a new consolidated console comparison.
4. Benchmark FC27 at 1440p / 1×, same scene, logging OFF, fresh vs retained caches controlled separately. Compare late50/late100/worst, missing HUD pixels, gameplay controls and safe shutdown.
5. Keep F07 open while substantial judder or blank/delayed HUD persists; preserve F01–F06 contracts, no forced 60 FPS or shader skipping.
6. If a source was already inspected and unchanged, do not restart its entire audit without a new regression signal. Prior evidence maps: `FC27_GPU_SOURCE_TARGETS_2026-10-21.md`, `FC27_F07_STUTTER_HUD_PRIORITY_2026-10-26.md`, `EDEN_OPTIMIZATION_WORKLIST_2026-10-20.md`.

## F07: shader completion publication (source fix after the first cross-system pass)

`GraphicsPipeline` sets `is_built=true` with a **release** store after its Vulkan pipeline handle is constructed. Two readers test the status before accessing that non-atomic handle. `CanExecuteDraw()` already used **acquire**, while `IsBuilt()` still used **relaxed**: the latter did not establish the required publication ordering. The maintained PS5 native header and the pinned Vulkan generator now use **acquire** for `IsBuilt()`.

`check-ps5-f07-pipeline-publication-host.py` compiles both methods extracted from the actual native header, verifies the builder's release store, tests threaded release/acquire publication and failed-pipeline behavior under O0/O2. No shader is skipped, no new GPU wait is inserted, and no FPS claim follows from the memory-order fix.
