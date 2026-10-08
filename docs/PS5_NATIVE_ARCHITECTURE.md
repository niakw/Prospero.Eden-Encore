# Eden Encore — PS5-first execution architecture

Status: **engineering decision and source-only investigation**, 8 October 2026.
No new PS5 build, run, performance claim, or shipping change is authorized by this document.

## Decision: close FC27 A/B/C/D experimental campaign

FC27 title ID: `0100C49025D3E000`. The four tests used the same installed
emulator build but different time spans and potentially different match scenes.
These measurements are indicators, **not** matched deterministic benchmarks.

| Trial | Change | Duration | Presented FPS | 5s windows >=29.5 FPS | >100ms present gaps/min | JIT pressure/min | Worst gap |
|---|---|---:|---:|---:|---:|---:|---:|
| A | Default CPU + default JIT | 5m32s | 27.89 | 59.1% | 17.7 | 3.26 | 1098ms |
| B | +64 MiB A64 JIT | 18m56s | 28.48 | 68.1% | 7.34 | 1.43 | 617ms |
| C | +192 MiB A64 JIT | 19m45s | **28.63** | **72.5%** | **5.26** | **0.71** | 814ms |
| D | Logical CPU placement, default JIT | 19m11s | 27.95 | 61.6% | 8.29 | 2.09 | **574ms** |

Source: user's October 8 PS5 `heap.log` / `stderr.log` captures.
D config explicitly says `jit=0 cpu_logical=1 vulkan_trace=1 safe=0`.
D `EDEN_WORKER_TOPOLOGY ready=0 distinct_cores=1`, but
`EDEN_EXPERIMENT_CPU result=enabled physical_verified=0 logical=0,3,6,9,12
secondary_mask=db6` with successful CPU pin attempts. These prove logical
affinity calls worked, **not** that separate *physical* Zen 2 cores are used.
D has 40 JIT pressure events and 159 >100ms present gaps in ~19m11s.
Of 38 five-second windows below 25 FPS, 19 were not within ~6 s of a
recorded JIT pressure event (approximate temporal alignment): JIT growth
alone cannot explain every drop.

**Disposition:** no extra E/F/G gameplay tuning profiles. C is the best
observed trial, not an automatically shipped default. D does not establish
a general CPU affinity improvement. Preserve raw A/B/C/D observations and
the verified production rollback.

## PS5-first, not naive PC assumptions

The upstream Switch emulation stack was developed primarily for general
desktop operating systems. The Encore/Prospero port already has meaningful
PS5 adaptations (native GPU integration, RX/RW JIT aliases, native memory
mapping, sparse guest page tables, A32 fastmem, worker/topology probes).
So the problem is **not** literally an unmodified desktop binary or proof
that a previous maintainer ignored console constraints. However, remaining
desktop-oriented allocation, threading, rendering and frame metrics must be
reviewed against the actual firmware 13.60 environment.

The goal is to use *the resources exposed and available to the PS5 process*
as efficiently as possible, not to force every physical CPU/GPU/memory unit
to 100% utilization. Console OS services, the emulator's guest state, host
graphics and driver resources share finite resources; unused capacity is
not evidence of underutilization, while saturated queues are not proof of
better performance.

## Required architecture

### A. Host CPU and guest progress

- At session start discover the **allowed affinity mask** and distinguish
  OS logical CPU identifiers from verified physical topology.
- Map and time the actual critical path: guest CPU cores, guest idle/spin,
  rendering handoff, GPU worker, frame completion, HLE services, shader
  pipeline builders, audio and I/O. Observe contention and latency, not
  just total CPU usage.
- Replace unconditional worker fan-out and guessed pinning with workload-aware
  thread pools and CPU reservations **only where measured**. Keep successful
  OS default scheduling when physical topology is unknown.
- Preserve correct guest synchronization / timing and ability to shut down.
  More threads on the same physical core can worsen frame time.

### B. CPU JIT code lifetime and physical memory

- Separate **code address-space capacity** from **physically committed RAM**.
- Stable dual RW/RX views and incremental mapping must preserve executable
  pointer validity, W^X ownership and active-worker safety.
- **No arbitrary fixed total 4 GiB ceiling**: the earlier 4 GiB tier has
  been removed from the branch. Do not promote another fixed ceiling.
  Growth must be demand-driven with multi-segment/far-jump-aware strategies
  when a single x64 rel32-sized code arena is exhausted. Merely raising
  `code_cache_size` infinitely is not viable.
- Determine an allowable **physical** budget dynamically from actual memory
  pressure and guest/GPU reservations; no assumption of all advertised
  16 GiB being available to the process.
- Policy: re-use code; avoid whole-cache evacuation; reclaim safely under
  memory pressure; never abort the running game solely because one optional
  JIT segment failed. Support low-memory fallback.
- Record reserved/committed/high-water/evictions/compile costs per title and
  core, with bounded log growth.

### C. GPU and graphics path

- Time guest GPU commands, Vulkan/RADV/AGC queues, CPU-GPU sync, shader
  compilation and framebuffer/display present *independently*.
- Remove redundant copies/barriers and unnecessary stalls only after
  correctness evidence. Preserve shader caches across sessions.
- Upscaling, internal resolution and filtering are an independent quality
  track: current FC27 test used 1x + Bilinear + FXAA, output 1440p.
  A 1440p signal is not 1440p internal detail.
- Adaptive quality should account for **measured GPU and memory headroom**
  and title compatibility, not automatically upscale while guest CPU hangs.

### D. Frame pacing and liveness

- Host-present 30 FPS != guest game progress. Measure actual guest simulation
  progress, frame production, CPU/GPU stalls and presentation timing.
- Separate short compile hitches, multi-frame stretches at 15–25 FPS, and
  true unresponsive guest hangs. Frame synthesis is not a substitute.
- Observe tail distributions (p95/p99 frames and >50/100/200ms events),
  controller-to-display latency where technically possible, and long-session
  stability. Avoid modifying timing semantics without evidence.

### E. Profiles and UX

- One automatic, safe PS5 execution policy across titles; verified
  title/version hints only where useful, **not** user-facing JIT trial modes.
- No further A/B/C/D variants or UX redesign; launcher is approved.
- Keep classic reliable runtime as fallback and isolate all new allocator
  work until a native compiler, W^X, OOM, relaunch and firmware 13.60
  qualification pass.

## Source audit — PS5 resource ownership and pipeline workers

**2026-10-08 source facts, not PS5 speedup claims**

- Upstream `vk_pipeline_cache.cpp::GetTotalPipelineWorkers` on desktop uses
  `max(2, hardware_concurrency()) - 1`. In D, 15
  `VkPipelineBuilder` workers were registered. They are low-priority and
  may sleep when there is no work; merely counting threads is NOT evidence
  they were actively using 15 CPUs.
- On this isolated PS5 branch, the derived source in
  `tools/prepare-vulkan-port.py` automatically budgets shader workers
  against guest and GPU threads: for a 16-logical-CPU report,
  `(16 - 6)/2 = 5` background compiler workers. No user-facing
  setting, no launcher change. This policy is **NOT** validated for shader
  loading duration, pipeline readiness, 30 FPS pacing, hardware topology or
  full hardware utilization. The number of compiled tasks is unchanged;
  lower parallelism might lengthen cold shader preparation.
- The PS5 Vulkan runtime's initial `EDEN_VULKAN_MEMORY` D report includes
  8 GiB of local Vulkan heap, ~6 GiB device-accessible memory and ~6.9 GiB
  observed direct-memory availability. These are **driver/device budgets**,
  not proof that PS5 has only 8 GiB physical RAM or that the GPU is idle.
- In `tools/prepare-vulkan-port.py`, `Device::GetDeviceMemoryUsage`
  derives a cache-budget usage estimate from the **largest contiguous free
  direct-memory block**, not the total free bytes. Fragmentation can reduce
  this number without an equal rise in committed memory. The GPU diagnostics
  already enumerate `sceKernelDirectMemoryQuery` regions and report
  `EDEN_PERF_DIRECT total / largest_free / free`, but A/B/C/D release logs
  do not establish the total-free versus largest-free trend over time.
  Do **not** blindly expand GPU heap sizes or loosen eviction until actual
  committed RAM, fragmentation, queue stalls and allocator failures are
  correlated. A wrong liberal budget could cause out-of-memory crashes.
- The normal CPU clock self-test reported `valid=0`, so its per-thread
  utilization estimates cannot justify claims that PS5 CPU/GPU cores are
  mostly unused. Fan noise or case temperature is not a telemetry reading.

**Direct next engineering step:** give the GPU cache-budget policy a
fragmentation-aware notion of *total usable bytes* alongside the largest
available *contiguous* allocation, with bounded sampling cost and a safe
fallback. Then address measured rendering queue stalls and guest liveness
before increasing internal resolution. Test load time as well as gameplay.

## Implementation checkpoint — automatic policy and protected diagnostics

- FC27 is automatically assigned the observed best C *cache capacity*
  (320/256/256 MiB for A64 cores 0–2) on this branch. No new player-facing
  A/B/C/D setting is added. It is an interim title-specific capacity hint,
  not the final demand-driven multi-segment allocator. **Safe Launch** keeps
  the qualified baseline (256/192/192 MiB). Until an app is compiled and
  installed, the player's existing PS5 build is unchanged.
- Reading `experiments.json` for A/B/C/D is now restricted to developer
  profiling builds via `EDEN_DEV_PROFILE`. Ordinary app builds ignore the
  now-completed tuning file. The incomplete sparse JIT path additionally
  requires explicit build opt-in `EDEN_SPARSE_JIT_DEV=ON`.
- `EDEN_MEMORY_LAYOUT` is emitted on the core-initialized and core-shutdown
  lifecycle boundaries (not per frame). It reports the kernel's largest
  available contiguous block and a conservative `free_upper` derived from
  scanned direct-memory regions. That upper bound is **not** used for GPU
  eviction, because the kernel's region enumeration may be incomplete.
- The source-only Vulkan worker policy logs `EDEN_PS5_SHADER_WORKERS` once
  when the pipeline cache is constructed, to reveal the actual selected pool.

These are source-level changes; no native build or firmware-13.60 runtime
validation has been completed. No general FPS improvement is claimed.

## Immediate implementation gates

1. Audit physical memory ownership and executable page-map APIs; do not
   merge `dev/ps5-sparse-jit` prototype until deterministic fixed-VA alias
   and out-of-memory behavior are proven safe.
2. Implement repeatable low-overhead telemetry for guest liveness,
   JIT evacuations, actual worker contention, driver queue waits and
   memory committed. No debug logging flood.
3. Replace single-region fixed JIT cache allocation with supported,
   demand-driven multi-segment memory and graceful pressure fallback.
4. Correct thread placement based on real firmware masks/topology or
   retain OS scheduling when unverifiable.
5. Target measured GPU bottlenecks, then separately raise image quality
   with fidelity tests.
6. Only after all gates: native build, hardware validation and decision
   to promote to production, with explicit rollback. No release claim
   until that point.

Tracking: docs/FC27_EXPERIMENTS.md, docs/PERFORMANCE_ROADMAP.md,
GitHub issue #8 (sparse JIT qualification). This file is a design decision,
**not evidence that those implementation gates already passed**.
