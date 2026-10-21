# FC27 — 21 October 2026: ranked native hot-path targets

Branch: `dev/ps5-sparse-jit`. This is a **specific execution plan**, not a
claim of gameplay improvement. No cache mutex, fence, guest invalidation, JIT
allocation policy, shader ordering or graphics-accuracy setting is loosened.

## Provenance — two different binaries

The historical detailed console trace
`heap.prev(20261021-171104).log` identifies executable
`5629395324ff65c98b50c44f35f2142a4a92654a`, JIT `sparse=1`;
the later quiet trace `heap(20261021-171104).log` identifies executable
`c3ac33ad61467bfeec5142806e2df89b90706284`, JIT `sparse=0`.
These cannot be treated as a matched A/B test of JIT, source changes or
telemetry overhead. Logs remain private; this document holds aggregates and
source anchors only.

The detailed trace contains **232 5-second windows**, 33,997 presented frames,
**466 intervals >50 ms**, 49 >100 ms, and a maximum of 1,095.734 ms.
The quiet trace contains **270 windows**, 39,286 frames, 873 >50 ms, and a
maximum of about 809 ms. Both are user-reported as perceptibly stuttering.
Presentation intervals are not guest simulation freshness.

## P0 — buffer-cache writer-vs-draw mutex contention

**Direct measurements:** `EDEN_GUEST_CACHE_DOMAIN domain=buffer`: 1,005,680
blocked acquisitions and 9.311 seconds of summed wait. Texture domain:
66,038 blocked acquisitions and 1.080 seconds. The total
`EDEN_FRAME_PRESSURE cache_wait_ms` sums to 10.391 seconds. These are
per-thread accumulated waits; do not substitute them for wall-clock frozen
game time. The five-second buffer-wait correlation with `late50` is
approximately **+0.325**, versus **+0.101** for texture waits.

**Exact native owners:**

- `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp:
  RasterizerVulkan::OnCPUWrite` (~1077–1120): locks
  `buffer_cache.mutex`, invokes `buffer_cache.OnCPUWrite`, may invoke
  `BufferWriteAhead::MarkFollowingPages`, then locks the texture cache
  and invalidates shader code.
- Same file, `RasterizerVulkan::PrepareDraw` (~265–418): owns
  `std::scoped_lock{buffer_cache.mutex, texture_cache.mutex}` over
  `pipeline->Configure`, dynamic states and draw-command recording.
- `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp:
  GraphicsPipeline::ConfigureImpl` (~445–690) performs descriptor image
  lookups, graphics buffer updates and descriptor binding **inside** that
  cache lock pair.

**Concrete development target:** shorten CPU-exclusive sections of
`ConfigureImpl` by moving only demonstrably immutable, allocation-only
preparation before the pair, and leave texture descriptor reads, buffer
upload/invalidation and GPU fence acquisition ordered correctly. Existing
`PreflightDescriptorScratch` and preflight GPU drains already implement
parts of this: do not duplicate them. Validate with real source-extracted
concurrency fixtures and retained buffer/texture ownership.

**Two high-stress windows:**

| Frame (end of window) | FPS | late50 | Buffer wait | Texture wait | JIT time | GPU dispatch |
|---:|---:|---:|---:|---:|---:|---:|
| 14238 | 18.908 | 58 | 70.50 ms | 4.50 ms | 18.81 ms | 1529.92 ms |
| 15037 | 19.798 | 52 | 252.24 ms | 8.41 ms | 33.57 ms | 1855.35 ms |

In the older trace, `EDEN_DEV_GPU dispatch_calls` per-window delta
correlates ~**+0.553** with `late50`; draw count itself does not.
`gpu_full_ms=0` in all sampled windows: **do not enlarge the 32-item
GPU queue as a performance fix**. Queue bursts and workload are associated,
but the blocked-buffer time does not directly explain every late interval.

## P1 — graphics configuration inside the paired locks

Across ~1.117 million 1-in-16 sampled draw instances:

| Source measurement | Mean per measured draw | Max recorded sample |
|---|---:|---:|
| `pair_held` | 6.337 µs | 1920 µs |
| `pipeline_configure` | 5.895 µs | 1916 µs |
| `bind_stage_descriptors` | 1.758 µs | 75.3 µs |
| `fill_views` | 0.872 µs | 1886 µs |
| `graphics_buffers` | 0.558 µs | 30.4 µs |
| `texture_cpu_refresh` | 50.1 µs (793 samples only) | 1039.8 µs |

These phases overlap (e.g., `pipeline_configure` includes subphases).
Never add them together as independent time. Sampling is conditional and
not a microbenchmark proving a direct frame-time saving.

**Precise investigation:** `GraphicsPipeline::ConfigureImpl` handles
`texture_cache.FillImageViews`, `buffer_cache.UpdateGraphicsBuffers`,
and `PushImageDescriptors` under the paired lock. First inspect per-stage
descriptor reuse and CPU-write contention against this exact call path,
not generic Vulkan frame pacing or cache allocations.

## P1 correctness — persistent HUD and damaged jersey regions

Old trace `EDEN_GPU_DRAW_DROP` records **zero** rejected pipeline,
configuration, descriptor-buffer and worker-pipeline draws. This excludes
those counted omissions, **not** stale/incorrect texture data or draw
contents. Texture budget near the end: 3.19 GiB used, critical ~5.20 GiB,
`memory_short=0`; there is no logged pressure-triggered texture OOM.

**Exact source owners:**

- `vendor/encore-active/eden-core/src/video_core/texture_cache/util.cpp:
  IsValidEntry`: maintained CMake-selected TU was missing the R312 invalid
  TIC/non-sparse-first-page guard. Repaired in `c5bff47e` and guarded by
  `tools/check-ps5-active-texture-descriptor-host.py`.
- `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h:
  TextureCache::VisitImageView, FillImageViews, CheckFeedbackLoop`.
  R314 NULL-view remap and feedback-view-key handling **are present**.
- `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp:
  GraphicsPipeline::ConfigureImpl, PushImageDescriptors`.
- `vendor/encore-active/eden-core/src/video_core/memory_manager.cpp`
  and pinned GPU remap invalidation backports for guest alias changes.

**Acceptance:** test invalid descriptor recovery without manufacturing
textures or silently bypassing invalidation. Count real draw omissions and
verify HUD, jersey, pitch and feedback image content on console. A green
host unit test is not this visual proof.

## P2 — first-use shader wait, then presenting a stale guest scene

- `vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp:
  PipelineCache::CreateGraphicsPipeline / BuiltPipeline`.
- `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp:
  GraphicsPipeline::ConfigureDraw`: on an incomplete async build it enqueues
  a scheduler callback waiting for `build_condvar`.
- `vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp:
  Scheduler::WorkerThread`: ordered scheduler execution can be held up by
  that callback. An arbitrary bypass would lose valid HUD/jersey draws.
- `vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp:
  PresentManager::GetRenderFrame`: cumulative frame-fence wait ~2.651 s in
  the detailed trace, not enough evidence to designate fences as the main
  sustained stutter source.

`jit_ms` correlates only +0.099 with `late50` across these windows,
although there are large **startup** JIT spikes. The historical sparse
session still stuttered badly; enabling sparse by default is not an
evidence-based GPU/HUD correction. Preserve explicit DEV qualification.

## Ordered engineering decisions and validation gates

1. **P0:** reproduce/verify locked owner code under 5-second late-frame
   clustering; optimize real `ConfigureImpl` paired-lock hold while
   preserving guest CPU write, texture and shader invalidation order.
2. **P1 correctness:** validate active TIC guard compilation in the native
   image, plus NULL-view recovery, feedback barriers and descriptor
   lifetime under remap. No automatic dropped-draw workaround.
3. **P2 shader:** quantify first-use shader worker waiting versus game
   content freshness, not merely Vulkan presents.
4. **P2 memory/JIT:** compare dense/sparse only with same SHA, scene,
   graphics settings and per-core compilation counters.

Host regressions **and** a green native app package are required before
console qualification. Console target: materially reduce `late50/100`,
worst interval, and visible scene repetitions while recovering HUD,
jersey and pitch fidelity. The already observed non-crashing shutdown
must not regress. Until these measures move, no performance win is claimed.

The CI parity oracle must also understand its exact source newline and
reverse only the reviewed PS5 TIC delta for the old R428 ASTC git-blob
witness. Do not bypass or disable that fail-closed test.
