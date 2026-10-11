# R313 / FC27 experimental PS5 Vulkan fast-first pipelines

## Root and expected impact

Pinned Eden `PipelineCache::BuiltPipeline` can return `nullptr` for an
unbuilt asynchronous graphics pipeline with a draw of >6 indices/vertices.
That render command is skipped. This is a **real source-level path for transient
missing geometry** while shader compiles, including potentially motion-specific
jersey, pitch or other materials. It does **not** prove FC27 HUD issues are
solely shader-related; R310 also logged invalid TIC format 0 and guest
mapping faults.

The first available Vulkan pipeline is ordinarily fully optimized, which
adds driver compilation time before a newly encountered material can draw.

## R313: bounded first-use compilation (experimental only)

Adapted from Mihawk's PS5 quick-first Vulkan idea with PS5-specific safety
controls and reduced steady-state work:

- On a **new runtime pipeline** (constructor's worker_thread != null) when
  R313 fast-first mode is enabled, create a real usable pipeline with
  `VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT`.
- A **single background optimizer thread** produces the normal optimized
  Vulkan pipeline for later shader binds. It does NOT skip synchronization or
  use placeholder materials. First-use output is correctly drawn by a
  genuine Vulkan graphics pipeline with the original guest shader modules.
- **Disk-loaded pipelines are excluded.** They have worker_thread==null and
  build their usual optimized Vulkan pipeline exactly once, avoiding startup
  double compilation of FC27's previously saved 356–359 pipelines.
- OptimizeState heap allocation is lazy and limited to runtime fast-first
  pipelines, not hundreds of preloaded shader cache objects.
- A shared lifetime state cancels queued jobs before touching a destroyed
  GraphicsPipeline. Active jobs set running=true; the destructor waits until
  completion. The optimized pipeline handle is published with atomic release
  and consumed on the GPU recorder with atomic acquire. Both handles stay
  alive until the pipeline object's safe destruction.
- Optimization failure retains the correct first-use pipeline; completion
  notifies the destructor even for unknown std::exceptions.
- **Do NOT copy** Mihawk's `VulkanTimer(24)` sample: the Encore cost array
  has 24 entries, indices 0–23. No out-of-bounds performance timer.
- No change to graphics cache mutexes, texture consistency, Vulkan barriers,
  JIT shared-code memory, dispatch cadence (64, hard 512 flush), or Sony
  reserved PS5 system RAM.
- **R313 all-on dev only**: default ON for EDEN_DEV_PROFILE, default OFF for
  shipping/no-dev builds. Per-title `dev-settings.txt fast_pipelines=off`
  restores the original optimized-first behavior. Reset between titles.

Expected: reduce time a brand-new shader draw is skipped and move expensive
optimization out of the frame's critical path. **Unverified**: on console, a
background worker could still contend with guest JIT, GPU driver pipeline
creation may not benefit from the disable-optimization flag, and other causes
of stutter / terrain shimmer remain.

## Validation

`tools/check-ps5-fast-first-pipelines.py` extracts the exact new
`GraphicsPipeline` queue/destructor/worker C++ body from the production
generator, compiles it under C++20, and exercises 100 instances that either
finish normally or are destroyed while the optimize job is queued. It also
checks release/acquire publication, one worker, single fast-first flag,
runtime-only path, lazy state allocation, no index-24 timer, and both source
and user-setting wiring. Both core source CI and native PS5 build run it.

R313 native CI must additionally verify the adapted pinned source compiles and
links on PS5, and that the actual all-on ZIP retains
`/data/homebrew/PPSA99008/eboot.bin` and `sce_sys/param.json titleId`.

Do not claim a measured FPS gain, new PlayStation controller glyph behavior,
or resolved FC27 crash/texture/HUD until hardware validation. User has ended
the three R310 hardware tests for the night.
