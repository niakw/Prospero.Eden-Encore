# R386 — FC27 R384 frozen match forensic findings (October 12 2026)

**Inputs:** uploaded `heap(10).log`, `heap.prev(3).log`, boot traces, stderr, and network-denied logs. R384 SHA `fa2ad53c79f1f8039c29e60917491d671539e3f0`; prior R370 SHA `40635302daf2ef6ee852c345ded42aa5b0d6d05f`. This report was generated OFFLINE from user-supplied logs; no PS5 network operations or native compilation.

## New finding: alive emulator, apparently stalled guest match

R384 has 294 ~5-second frame windows, average 29.021 FPS, 896 >50ms frames, max 625.872ms, final cumulative frame **42,823**, queue_full **0**. R370 previous session has 240 windows, 28.456 FPS, 1,060 >50ms frames, max 2,631.25ms, final frame 34,319. **These averages cannot be interpreted as an A/B improvement because R384 spends several minutes rendering the same workload while the user reports a frozen match.**

The final **70 consecutive five-second windows (~350s)** of R384, from around frame 32,436 to 42,823, show near-perfectly repetitive ratios: ~**294 Vulkan draws**, **444 guest CPU writes**, **48.5 IPC calls** and **18 R382 pre-dispatches** per frame, at steady 30 FPS and *zero >50ms frames*. Guest CPU sample epochs 0/1/2 reach epoch 293. The host controller keeps polling (polls=358,750, errors=0) even though button-edge counters stop changing in the final segment. No fatal signal is recorded.

The guest CPU PC samples collapse from 89/57/73 unique addresses in the first 100 five-second windows (cores 0/1/2) to only **9/7/6** unique addresses in the final 70. Core 0 repeatedly samples PC `0x8edbce14` in **55/70** windows. `IHardwareOpusDecoder` command 9 stops increasing near the same phase (126,981 cumulative calls), while IAudioOut, nvdrv and guest IPC calls continue. This strongly suggests a guest-side state/loop transition, but the PC addresses are not symbolicated and audio inactivity alone is not proof of deadlock.

This is **not a host process crash or a stopped Vulkan worker** in the supplied evidence: guest logic may be stuck, a scene may be repeatedly redrawn, or the guest may intentionally be idle. **Workload equality does not prove identical pixels** without framebuffer evidence. Crucially, existing `headless/stall_watchdog.h` only diagnoses stalled GPU command/draw progress, so it will miss this *progressing GPU with apparently frozen gameplay* case. Do not force-reset, alter fences or classify guest deadlock from FPS alone.

## R382 command chunks

The total `EDEN_SCHEDULER_PREFLIGHT` counter is **942,036** (~22 events/displayed frame overall; ~18/frame during final invariant window). These are software `Scheduler::DispatchWork` command-chunk sends, **not 942,036 Vulkan hardware queue submissions**. The 32KiB chunks reserve 4KiB outside cache locks. More queue_mutex traffic is plausible, but causal attribution for the game freeze is unsupported. Measure queue depth, actual DispatchWork cost and batch utilization before modifying threshold. Worker is not starved: regular GPU draws continue, and gpu_queue_full=0.

## Sony CPU topology / SMT

Actual native app allowed `0x1fff` (CPUs 0..12); game threads pinned to `0,3,6,9,12`; secondary mask `0xdb6` (CPUs 1,2,4,5,7,8,10,11). On the **unverified** adjacent SMT pairs (0,1), (2,3), etc, CPUs **1,2,7,8** are physical siblings of guest critical threads. Thus `logical_isolated=1` does **not** establish physical isolation. Both scheduler sysctls return ENOENT; AMD CPUID reveals 13 separate IDs and x2APIC collapses all 13 into one, both rejected by current correct fallback. Relevant PS5 reference: `premohq/PS5CEMU-HAR` uses Sony's `sceKernelGetCurrentCpu` and `scePthreadGetaffinity`. Next probe should log Sony current CPU before/after pinning and raw CPUID subleaf data, restore exact affinity and never publish unverified SMT pairs. Do NOT enable new physical pinning yet.

## Other observations

`stderr` reports the game actually launched with **1x game resolution, bilinear upscaling, FXAA, 1440p output**: low source resolution can explain part of the soft/pixelated look, not missing/flickering HUD textures. Network DNS denials to EA endpoints are present but not proven causal. R384's original startup successfully compiled/loaded its shader cache; no fatal error or heap exhaustion stands out from this evidence.

## Next work — no redundant user tests

1. Detect long, nearly invariant guest workload in OFFLINE analyzer and later a **diagnostic-only** once-per-5s console probe; no auto-restart or forced crash.
2. Verify Sony current CPU / per-affinity CPUID identity before any SMT-aware pinning.
3. Measure real Vulkan worker chunk queue cost and distinguish early pre-dispatch from GPU queue submits, keeping original GPU execution ordering.
4. Investigate HUD texture correctness separately from output upscaling.
5. Compile only one combined, validated PS5 package when actionable fixes are ready.
