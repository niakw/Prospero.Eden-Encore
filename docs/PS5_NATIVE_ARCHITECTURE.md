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

- **All PS5 guests, both A64 and A32, use one continuously sized JIT
  memory policy**, chosen once before CPU startup from the kernel's largest
  available contiguous direct-memory block. A 3 GiB physical headroom floor
  protects shared guest/GPU/system allocations; half the remaining allocatable
  contiguous pool defines the initially dense code-memory budget, split over
  guest cores by ISA-dependent workload weights. Unlike the retired A/B/C
  tiers, usable budgets may exceed FC27's 320/256/256 MiB C sizes. Unknown
  memory availability and **Safe Launch** revert to A64 256/192/192 and A32
  512/64/64 MiB. The policy is in the normal release path, independent of
  ROM ID or user profile and applies only to the **active** guest ISA.
  Per Xbyak code arena a 1536 MiB branch-addressing guard remains. This is
  not a global total-JIT ceiling: removing the per-arena constraint requires
  additional code segments and safe branch trampolines. Physical backing is
  **still eagerly allocated** by the active allocator. The sparse prototype
  is developer-only until aliasing, mid-game OOM recovery and code-pointer
  lifecycle are proven. No new UI performance switch was added.
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

## Safety and host contract updates (source only)

- The `GetTotalPipelineWorkers` PS5 derivative now reads the **actual
  schedulable logical CPUs** using the firmware CPU-affinity mask, with
  a conservative fallback if affinity reporting is unavailable. This
  replaces the desktop `hardware_concurrency() - 1` assumption for
  background shader compilation. Physical Zen2-core topology is still
  unverified, and these thread counts have not been benchmarked.
- Fixed an unreachable diagnostic: the original `game_loaded` phase
  never occurred in `passed(...)`. Memory snapshot calls now use real
  lifecycle phases **`core_initialized`** and **`core_shutdown`**.
- The developer-only sparse JIT first uses a disposable 2 MiB fixed-VA
  RW/RX alias check and returns to dense allocation if the test fails.
  It tests mapped-data visibility and RX protection, **not actual
  execution or the safety of a mid-session OOM**. The prototype still
  fails closed on a mapping/commit error while emitting code; do not
  enable it in a release build.
- `EDEN_JIT_SPARSE_MEMORY` lifecycle summaries now distinguish **virtual
  reserved** from **physical committed** memory, under a mutex. These
  diagnostics are not called on the rendering hot path.
- Added `python3 tools/check-ps5-architecture.py` for offline source
  invariants, including lifecycle stage reachability, compiler gating,
  PS5 affinity headers and the absence of the old fixed 4 GiB tier.
  This is **not** an emulator test or PS5 hardware qualification.

## Shader compilation persistence (all titles; source only)

- **RADV/Mesa:** `MESA_SHADER_CACHE_MAX_SIZE` scales to the actual cache
  filesystem's writable free storage (currently one eighth of its available
  space, fallback 256 MiB if the query fails). The former hard 256 MiB quota
  repeatedly evicted compiled driver shaders despite free writable storage.
- **Native OpenGL:** `TrimShaderCache` no longer deletes compiler records
  whenever its directory grows beyond 64 MiB. Between sessions it retains
  valid shader records unless filesystem free space falls below a reserve
  appropriate to the installation (32 MiB to 1 GiB), then removes the oldest
  eligible cached records first. Failed free-space query => no speculative
  deletion. These disk policies do not allocate extra VRAM and do not alter
  the frame hot path.
- Host-only C++ regression gates:
  `tools/check-jit-memory-policy.py`,
  `tools/check-shader-cache-pressure.py`.
  Code remains uncompiled and untested on PS5 firmware 13.60.

## Sparse JIT recovery and physical usage (source-only, 2026-10-08)

The developer-only sparse JIT now commits a 4 MiB bootstrap before returning
the two code addresses. This is necessary because upstream Dynarmic's constant
pool writes approximately 2 MiB before the enclosing `BlockOfCode` constructor
enters `EnsureMemoryCommitted`. Sparse VA reservation or bootstrap failure
releases the reservation and attempts the original dense allocator; a per-region
ownership lookup prevents committing sparse pages into dense aliases.

Once a guest is running, an unfulfilled `sceKernelAllocateDirectMemory`
request **before page mapping** throws `std::bad_alloc` from the derived
`EnsureMemoryCommitted`. A64 and A32 attempt the existing Dynarmic cache
invalidation/rewind, then retry once using physical pages already owned. A second exhaustion failure still propagates. For an uncommitted chunk,
failure at RW mapping, RX mapping or executable permission now attempts
to replace **only the new** RX and RW mappings with anonymous `PROT_NONE`
guards, releases that chunk's direct memory, and returns failure without
touching previously committed JIT code. If fixed-address restoration cannot
be proven, the process aborts rather than reusing an ambiguously mapped
executable page. This recovery is **source-level / host-mocked only**;
the firmware 13.60 fixed-map behavior is not qualified, and sparse remains
disabled in normal builds. The code must not be
advertised as unconditional OOM safety.

Ordinary dense JIT allocations now keep a separate counter of *physical*
direct-memory bytes, including allocator overhead, updated only on
allocation/deallocation. Lifecycle snapshots print
`EDEN_JIT_DENSE_MEMORY` and `EDEN_JIT_SPARSE_MEMORY` at
`core_initialized`, `core_shutdown`, and `core_destroyed`, enabling
post-session leak detection without per-frame polling.

`tools/check-jit-sparse-host.py` compiles the real PS5 memory source with
mocked kernel mappings to exercise alias visibility, constructor bootstrap,
incremental commitment, deliberate OOM and cleanup. This is wired into
lightweight/release preflights **but not executed in a GitHub runner or on
PS5 yet**. Existing `tools/check-jit-allocator.py` also asserts dense
physical-accounting returns to zero after every tested allocation/free.

## PS5-first vendor/runtime review — Dynarmic and Vulkan (8 October 2026)

- **Upstream snapshots are not authority.** The pinned Eden tree vendors
  Dynarmic, with substantial local CMake source transformations. Azahar's
  fork has commits dated 2026-06-24 and 2026-09-26, but a wholesale swap
  is **not** safe without comparing translation behavior, JIT pointer
  ownership, A64/A32 exclusives and Xbyak code-arena semantics.
- **Global Dynarmic startup recovery:** both 32-bit and 64-bit CPU cores
  retry a dynamically sized initial code arena when Xbyak reports
  `ERR_CANT_ALLOC` or C++ reports `bad_alloc`, shrinking only down to
  the original per-core tested size. Invalid code, protection errors and
  other unexpected exceptions still abort rather than being misdiagnosed.
  The 8 MiB null-JIT path is preserved. Host fixture:
  `tools/check-jit-startup-retry.py`.
- **Vulkan pipeline persistence:** the earlier PS5 Vulkan startup did not
  call the renderer's per-title shader cache setup, leaving the guest
  `pipeline_cache_filename` empty. The source now enables shader disk
  caching and Vulkan driver pipeline caching for all running games and
  initializes the per-title filenames **without bulk shader precompile**
  at launch. Unlike a naive timed cancellation, the lazy setup returns
  before `workers.WaitForRequests(stop_token)`, which would otherwise
  permanently request stop on the persistent compiler worker threads.
  Normal newly compiled shaders can be serialized across sessions.
  Previously persisted guest pipelines are **not yet prewarmed**.
- **RADV updates:** incompatible Vulkan driver cache initial data is
  caught at `CreatePipelineCache` and retried with empty cache data
  rather than failing game launch. A failure with empty data still
  propagates; stale data is discarded/replaced on subsequent saves.
  The pinned source transformation asserts its exact upstream anchor.
- CI source gates include `tools/check-vulkan-pipeline-persistence.py`
  and the A64/A32 fallback C++ host mock. **Neither a PS5 build nor
  firmware-13.60 hardware tests have been run for these changes.**

## Verified source-level defects corrected — global PS5 port

- **Native dense JIT W^X failure:** the previous allocator could publish a
  writable RW/NX address after the executable RX alias failed. The corrected
  code frees the direct allocation, decrements physical-memory ownership and
  returns null, allowing the existing bounded Xbyak startup retry. The native
  fault-injection test now rejects all such unsafe fallback paths.
- **Dynarmic generated translation-unit macro:** the parent CMake
  `PS5_NATIVE` variable was not necessarily a preprocessor definition for
  Dynarmic; `eden-headless` and `common` had explicit definitions, while
  the derived `BlockOfCode::EnsureMemoryCommitted` checked `#ifdef
  PS5_NATIVE`. The generated JIT source now receives `PS5_NATIVE=1`
  locally via its own CMake source properties, without redefining it on
  all vendored Dynarmic objects. Vulkan already defines it on `video_core`.
- **Vulkan driver binary cache serialization:** the pinned vendor overwrote
  `vulkan_pipelines.bin` directly, losing the previous good blob if the
  foreground process stopped mid-save. The native derivative writes a
  `.new` file, flushes/closes it, renames in the same directory, and
  serializes concurrent writers with a mutex. Failed saves leave the
  previous cache intact. This is process-interruption protection, **not
  guaranteed durability across sudden power loss**.
- Added an exact generated-function host gate
  `tools/check-vulkan-cache-atomic.py` to the source and native release
  preflight lists. Separately, host C++20 counterparts of the startup
  allocation fallback and transactional Vulkan write compiled and passed
  on Linux during this development pass. These do not establish native
  PS5 executable permissions, filesystem rename behavior, or FPS gains.
- No changes to the approved launcher or per-game A/B/C/D controls.

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

### Native dense executable-view sizing and teardown (8 October 2026)

The dense allocator may round a requested non-2-MiB JIT size to a
larger large-page direct-memory span. Its RX alias must be destroyed
using the **actual** mapped span from the direct-memory allocation
header, not a smaller page-rounded Xbyak request. The native source
exposes `Common::ExecutableAliasSpan(writable)` and records it in
`EdenJitAllocator` ownership, including the exception-cleanup path.
A host fixture exercises a 3 MiB request with a 4 MiB RX alias and
checks that the entire tail is unmapped at release. This is a host
ownership test, **not** a real PS5 SDK/hardware mapping qualification.
