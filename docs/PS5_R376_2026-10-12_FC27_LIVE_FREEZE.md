# R376 — FC27 live freeze, PS5 physical CPU topology and safe liveness witness

## Captured while the game was still frozen

The user reached the end of a match and reported a complete freeze in native R370. Read-only FTP captures were taken on October 12, 2026 at 15:05:48 UTC and 15:07:00 UTC. The immutable boot-trace and heap source SHA both prove R370 build 40635302daf2ef6ee852c345ded42aa5b0d6d05f. Local raw logs remain PRIVATE on the authorized Mac in /private/tmp/eden-r370-live-freeze.

The heap contains 240 five-second windows, 28.46 mean FPS, 1060 frames over 50ms, no GPU producer queue full. Last graphical report frame 34319: FPS 17.556, 71 long frames/5s, 16637 guest graphics-cache collisions, 273.609ms guest cache wait, zero producer-full time. Critical finding: the heap log remained exactly 2,912,214 bytes during the two frozen snapshots while stderr log grew from 78,478 to 81,098 bytes and the DualSense heartbeat progressed from 367,500 to 383,750 polls. The input worker stays alive while gameplay or GPU-frame reporting stops.

This is not a demonstrated renderer mutex deadlock. No live blocked thread stack or HLE syscall stack trace is available. It remains possible that a guest/HLE thread blocked the game, or that the GPU owner stopped for another reason. DO NOT force a mutex unlock, disable fences, or change texture/descriptor coherence merely because of correlation.

## R375 — dual read-only FreeBSD scheduler SMT discovery

Firmware 13.60 reported ENOENT (errno=2) for kern.sched.topology_spec; AMD CPUID reported 13 supposed physical IDs from 13 logical CPUs and x2APIC reported 1, both impossible, correctly rejected. FreeBSD scheduler code moved the ULE topology OID under kern.sched.ule.topology_spec in January 2026 and restored a legacy alias subsequently. Probe BOTH names with read-only bounded sysctl and exact XML SMT-group validation; fallback to physically unverified logical scheduling when both are absent. Never invent thread sibling groups or write kernel sysctls.

Mac source-extracted ASan/UBSan host affinity regression mocks legacy, ULE-only and absent sysctl cases and passes. Hardware support on Sony firmware is NOT YET confirmed.

## R376 — independent freeze witness

Every 5s GPU owner ReportGpuThread publishes its timestamp and frame through lock-free atomics, only with detailed logs enabled. Every 1250 controller polls, the already-existing input heartbeat reads those counters and, when the GPU report is stale at least 20 seconds, prints at most one EDEN_GPU_REPORT_STALLED warning per 30 seconds. Fields: age_ms, frame, gpu_ticks, draws, guest_writes, guest_reads, guest_dequeues, guest_ipc, cache_collisions. No GPU/cache locks are taken and no allocations or watchdog resets occur. Host source-extracted C++ regression tests threshold, startup suppression, clock rollover and quiet logging guards.

A later double snapshot of these counter values can distinguish whether the CPU guest and GPU tick continue while GPU frame accounting stops. It cannot by itself pinpoint a mutex owner. This is a corrective observability and CPU-platform compatibility release, not a validated solution to FC27 stutter/freeze.

Test once only after source/native GitHub workflows succeed, without suppressing crash logs or overriding graphical settings. The current captured frozen R370 logs remain valid and complete; the user may close the console game.

## R377 — bound the instrumentation perturbation of CPU guest writes

The first SHA-verified R370 match generated ~12.9 million guest OnCPUWrite callbacks, each using a DiagnosticTimer that wrote two shared atomic counters with detailed logs enabled. These writes can cause shared-cache traffic across three guest CPU host workers. R377 batches the SAME per-callback measured elapsed nanoseconds and count per thread, publishing to the existing atomic totals every 64 callbacks or on thread exit. ~64x fewer global atomic RMWs in the detailed profiler; quiet mode stays entirely untouched. At any five-second snapshot or freeze, guest-write cumulative totals may lag a maximum of 63 per active guest thread; the new independent pad GPU-stale witness remains valid. This is not a verified FPS speedup and does not change underlying buffer-cache critical sections or the unknown freeze HLE/GPU owner.
