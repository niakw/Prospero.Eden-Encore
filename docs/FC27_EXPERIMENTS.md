# FC27 — experimental performance A/B (PS5 firmware 13.60)

**PS5 build requested on the experiment branch; not PS5 hardware tested. OFF by default.**

Create `/data/prosperoeden/config/experiments.json` explicitly, after a build
containing the experimental code has been installed:

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

Change **one setting at a time**, then restart FC27. Safe Launch ignores
all experiments. Delete the game entry to revert everything.

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

FC27 provided the **A64 evidence**, but the branch no longer contains an
FC27-specific performance exception. Every PS5 game's A64 JIT follows the
same launch-time memory-admission policy: C/Expanded when enough contiguous
direct-memory headroom exists, B/Balanced with intermediate headroom, and
A/baseline when availability is low or cannot be queried. **Safe Launch
always uses A.** A32 guest caches retain their separate sizing until their
behaviour has been validated. The old `experiments.json` controls are
developer-build only. The policy is automatically selected in **normal build
code**, requires no player toggle and does not yet support online JIT growth.
Only FC27 has user-supplied comparative evidence for the C capacity;
other games have not been benchmarked with it. The installed app is unchanged.

## Sparse JIT memory (development branch only — not built or PS5-qualified)

The dense PS5 code allocator used by A/B/C/D commits **all** requested direct
memory at JIT creation, even when a small game uses only a fraction. This branch
prototypes a different backing scheme while retaining stable RX and RW views:

- `jit_memory: "sparse"` (only when compiled with `EDEN_SPARSE_JIT_DEV=ON`\n  and `EDEN_DEV_PROFILE`) reserves both virtual views, but
  commits 2 MiB *physical direct-memory* chunks only when Dynarmic calls
  `BlockOfCode::EnsureMemoryCommitted` before emitting code. It does not rely
  on execution-time page faults, change guest timing, or move existing code.
- The old 4 GiB fixed-capacity prototype has been **removed**: no arbitrary
  new total ceiling should become the architecture. The sparse prototype
  currently retains the tested A/B/C capacities while safe multi-segment
  auto-growth and actual memory-pressure controls are developed.
- The qualified A/B/C/D experiments remain dense and unchanged unless the
  new `jit_memory` option is explicitly enabled. A32/core3 retain their
  default capacity sizes, although their direct backing is also incremental
  while sparse mode is enabled.
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
