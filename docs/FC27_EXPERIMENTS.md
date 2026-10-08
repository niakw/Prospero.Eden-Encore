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
