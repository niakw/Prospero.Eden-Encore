# FC27 — experimental performance A/B (PS5 firmware 13.60)

> **Current 2026-10-09 test policy overrides the historical examples below.**
> `bash tools/build-package.sh dev <TITLE_ID>` now compiles the sparse page mapper and enables
> sparse JIT, logical CPU selection and Vulkan pacing diagnostics automatically
> for every title, without an Experimental menu switch or `experiments.json`.
> Safe Launch disables the extra test modes. Sparse additionally probes PS5 RW/RX
> alias support at runtime and reverts to dense if the probe fails.
> `release` and `release-stage` force sparse **OFF**; none of this
> creates or verifies PlayStation glyph artwork or unimplemented GPU operations.
> The source has not yet been built/qualified on firmware 13.60.
>

**Archive of the completed A/B/C/D campaign. Historical JIT tiers are retired; developer sparse mode remains unbuilt and unqualified on PS5.**

Historical `experiments.json` example from that campaign (not a recommendation for current builds):

```json
{
  "games": {
    "0100C49025D3E000": {
      "jit_cache": "balanced",
      "cpu_placement": "off",
      "vulkan_pacing": "off"
    }
  }
}
```

During the historical campaign, changes were tested one at a time with an FC27 restart.
Safe Launch ignores experiments. The retired `jit_cache` values no longer select
an A/B/C code cache size in the current development branch.

- `jit_cache`: `off` (default, A64 core0/1/2 256/192/192 MiB),
  `balanced` (256/224/224 MiB, +64 MiB), or `expanded`
  (320/256/256 MiB, +192 MiB). Core 3 (16 MiB) and A32 unchanged.
  Cache region size is set at JIT creation: this is **not online resizing**.
  Watch executable memory headroom, guest faults, cache evacuations and tail FPS.
- `cpu_placement`: `off` (default), `logical` (distinct OS logical
  CPUs if the physical x2APIC topology cannot be established; logs
  `physical_verified=0`). Logical placement is **not proof** of separate
  physical cores or safe SMT isolation; it might regress performance.
- `vulkan_pacing`: `off` (default), `trace` (passive histogram
  `EDEN_EXPERIMENT_PRESENT` for presentation intervals). This is a
  **measurement** of pacing, not an actual frame limiter or frame generator.
  No sleeps, extra GPU copies, guest-clock changes, or dummy frames.

Compare the *same* match and display/output profile at equal durations.
Record `EDEN_VULKAN_FRAME` (FPS, worst_ms, late50/100/200/500, streak),
`EDEN_EXPERIMENT_PRESENT`, `EDEN_JIT_PRESSURE`, memory and game progress.
A five-second window near 30 FPS can still hide stutter. A transient
increase in average FPS is not proof of resolved guest/JIT stalls.

No AMD FSR 3 optical-flow or FSR 4 ML frame generation is installed. Source
FC27 falls to 14–20 FPS, so 60-FPS synthesis is not an appropriate substitute
for fixing guest stutter. Shared-JIT, compile-ahead, unsafe CPU/DMA and inline
exclusives are still OFF by default. Require an explicit user-approved build,
standalone validation, and PS5 hardware A/B before promoting any setting.

## End of A/B/C/D campaign

FC27 supplied the **A64 performance evidence** that a larger code cache
can reduce eviction, but there is no FC27-specific exception or A/B/C fixed
ceiling in the current development branch. All PS5 titles, both A64 and A32,
now receive a continuous launch-time memory-derived code cache budget. Safe
Launch and unavailable memory measurements use the respective proven
baselines. The historical A/B/C/D tests remain documented here only;
The unified development test build automatically enables CPU/frame/sparse tracing; legacy `experiments.json` is ignored
but does **not** override the code cache capacity. This does not yet provide
mid-game growth, or prove all games benefit from larger dense allocations.
The installed PS5 app remains unchanged.

## All-title development experiments (source candidate, not PS5-qualified)

A development build compiled with `EDEN_DEV_PROFILE` can now apply the same
opt-in experiment to **every game** rather than requiring a manual title entry.
`defaults` applies to all titles (including ones without a known Nintendo title ID);
a field supplied in `games.<title-id>` overrides that one global field.
`"off"` disables an individual field inherited from `defaults`.
Unknown/missing fields keep the existing production behaviour.
Safe Launch ignores both the global and per-title values.

Example **for developer source review, not for installing on PS5 yet**:

```json
{
  "defaults": {
    "cpu_placement": "logical",
    "vulkan_pacing": "trace",
    "jit_memory": "off"
  },
  "games": {
    "0100C49025D3E000": {
      "cpu_placement": "off"
    }
  }
}
```

The all-title CPU setting is **logical-placement experimentation only**:
the x2APIC hardware report `ready=0` does not prove that the
guest runs on one CPU, nor that different OS logical IDs are different
physical cores. Sparse JIT is enabled automatically in the unified test package when compiled with
`EDEN_SPARSE_JIT_DEV=ON`, and it still requires the native alias preflight. The pacing
`trace` mode **only measures** frame time and never synthesizes FPS.
Do not turn these options on in a shipping release without a native PS5
test and regression comparison.

## Sparse JIT memory (development branch only — not built or PS5-qualified)

The dense PS5 code allocator used by A/B/C/D commits **all** requested direct
memory at JIT creation, even when a small game uses only a fraction. This branch
prototypes a different backing scheme while retaining stable RX and RW views:

- Sparse JIT (only when compiled with `EDEN_SPARSE_JIT_DEV=ON`
  and `EDEN_DEV_PROFILE`) reserves both virtual views. It commits an initial
  4 MiB bootstrap before Dynarmic construction (constant-pool initialization),
  then commits further 2 MiB *physical direct-memory* chunks on
  `BlockOfCode::EnsureMemoryCommitted` before emitting more code. It does not rely
  on execution-time page faults, change guest timing, or move existing code.
- The old 4 GiB fixed-capacity prototype has been **removed**: no arbitrary
  new total ceiling should become the architecture. The sparse prototype
  currently retains the tested A/B/C capacities while safe multi-segment
  auto-growth and actual memory-pressure controls are developed.
- Normal PS5 builds retain dense direct-memory mappings; the developer-only
  `jit_memory` option must be compiled and explicitly enabled before using
  the sparse prototype. A32/core3 retain their default capacity sizes,
  although their direct backing becomes incremental in sparse mode.
- During a session, committed chunks are retained across cache clears to keep
  JIT pointers safe. All owned chunks and both reservations are released only
  when the corresponding JIT is destroyed.
- Diagnostic records: `EDEN_JIT_SPARSE_RESERVE`, `EDEN_JIT_SPARSE_RELEASE`,
  `EDEN_JIT_SPARSE_OOM`, and `EDEN_JIT_SPARSE_COMMIT_FAILED`.

**The unified test build requires no experimental options in Settings.** This is source-only work;
the MAP_FIXED dual-alias path, executable permissions, physical-memory exhaustion,
fragmentation, teardown and repeated FC27 stress tests still require native
compilation and real hardware qualification. A failed mid-session direct-memory
commit deliberately fails closed rather than executing a partially mapped cache;
it is **not yet** a production-safe auto-sizing policy. There is currently
no unlimited executable-code allocator and no shipping auto-growth.


## Verified PS5 FC27 crash — 8 October 2026, build #37844050191

This hardware run is no longer speculative. User-supplied native crash files
`crash-20261008-234818.txt`, `*-stderr.log`, `*-heap.log` prove:

- FC27 `0100C49025D3E000` ran Vulkan/RADV, 1440p output, internal 1x,
  FXAA, PlayStation *input* profile. Compiled A64 **dense** JIT admitted
  approximately 4376 MiB of direct memory, with worker code arenas
  1536/1508/1304 MiB plus core3, after querying a largest contiguous
  free block of 11826 MiB. Sparse JIT was OFF (correct for release).
- Several minutes into a match the native direct allocator **rejected a
  440 MiB allocation** (`rc=80020023`), the operator-new handler logged
  `std::bad_alloc`, and the process terminated on `CPUCore_1`.
  Crash report: largest remaining free direct-memory block **38 MiB**,
  heap **1280 MiB**, five large blocks totalling **1016 MiB**.
  Do not equate 6 GiB advertised Vulkan VRAM to free physical RAM.
- Frame-present telemetry has genuine stutter under the nominal 30-FPS
  cap: 22.562 / 23.761 / 24.717 FPS five-second windows, worst frames
  above 200 and 300 ms. Stable 30-FPS windows cannot prove responsive
  emulated gameplay (guest CPU and graphics progress may diverge).
- Guest GPU shader translation reported missing `PRMT (imm)` and Fermi2D
  repeatedly reported `Source depth is not one`. These are additional
  graphics-compatibility concerns, **not proven to be the allocation
  that caused the process to terminate**.
- Launch log proves `Controller profile PlayStation` with empty custom
  map and `In-game button art: Nintendo original (rule=unsupported)`.
  The development branch explicitly disabled the last qualified
  `PlayStation Auto` gameplay switching. Restoring it is an input
  regression fix, **not** visual PlayStation glyph replacement: FC27
  has no verified RomFS artwork pack and the catalogue has no rule.

Root-level source response:
- `ChooseJitMemoryPlan` no longer physically commits HALF of the
  post-reserve pool for non-reclaimable dense JIT at game start. It
  admits a **quarter** at most and preserves the remaining three quarters
  for the guest renderer/graphics/runtime. This remains adaptive to
  the launch-time physical contiguous pool for **all A32/A64 games**,
  not title-based or the retired A/B/C tiers. The exact 11826-MiB
  hardware trace is a regression fixture.
- Restore `Pad::SetAdaptivePlayStation(effective_layout == 0 &&
  !custom_mapping)` from the last FC27 gameplay-qualified branch;
  preserve fixed custom mappings and explicit Nintendo mode. Add a
  source regression to stop future accidental deactivation.

**Qualification still required**: code host tests, new native SDK build,
repeat match with the *same* settings, late-memory exhaustion proof,
30-FPS responsiveness, and console-side controller behavior. These
changes are a diagnosis-driven **candidate**, not a claimed crash fix
until PS5 runtime passes. Do not clear or reset caches for the repeat.
