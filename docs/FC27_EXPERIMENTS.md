# FC27 — experimental performance A/B (PS5 firmware 13.60)

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
`experiments.json` can still control developer-only CPU/frame/sparse tracing
but does **not** override the code cache capacity. This does not yet provide
mid-game growth, or prove all games benefit from larger dense allocations.
The installed PS5 app remains unchanged.

## Sparse JIT memory (development branch only — not built or PS5-qualified)

The dense PS5 code allocator used by A/B/C/D commits **all** requested direct
memory at JIT creation, even when a small game uses only a fraction. This branch
prototypes a different backing scheme while retaining stable RX and RW views:

- `jit_memory: "sparse"` (only when compiled with `EDEN_SPARSE_JIT_DEV=ON`
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

**Do not activate the new flags yet on console.** This is source-only work;
the MAP_FIXED dual-alias path, executable permissions, physical-memory exhaustion,
fragmentation, teardown and repeated FC27 stress tests still require native
compilation and real hardware qualification. A failed mid-session direct-memory
commit deliberately fails closed rather than executing a partially mapped cache;
it is **not yet** a production-safe auto-sizing policy. There is currently
no unlimited executable-code allocator and no shipping auto-growth.
