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

## R378 — prevent indefinite asynchronous Vulkan pipeline wait after a worker exception

The exact compiled R370 worker contained an unbounded build_condvar.wait() when a first-use graphics or compute pipeline was not yet built. Async builder only completed the notification on success or a caught vk::Exception. However render-pass acquisition and Validate() ran OUTSIDE the graphics try, and both graphics and compute could throw other std::exception or other failures while creating state or collecting pipeline statistics. Exiting the worker without setting is_built=true and notifying can leave the GPU worker stuck indefinitely, even while the DualSense polling worker remains alive. This is a source-proven potential freeze, NOT a proven runtime call stack from the R370 frozen FTP logs.

R378 uses SCOPE_EXIT in graphics AND compute builders to ALWAYS publish release-order is_built=true, build_condvar.notify_all(), and exactly one shader_notify->MarkShaderComplete() after build worker exit, including non-Vulkan exceptions and early returns. Both constructors catch std::exception and unknown exceptions; failed builds keep pipeline==nullptr and existing draw/dispatch omission guards, never use an uninitialized handle. Pipeline statistics are collected only with a valid handle. Shader/descriptor/fence/cache mutex and GPU state logic remains unchanged.

New real-source-extracted ASan/UBSan tools/check-ps5-pipeline-build-wait.py tests both worker cleanup scopes with actual condition_variable, success, standard exception, nonstandard exception, early return and null notifier. Host C++ test passes. GitHub source and native PS5 CI remain required. No FPS or freeze cure is yet proven on the physical PS5.

## R379 — FreeBSD 11.4 scheduler XML topology parser repair

The user found releng/11.4/sys/kern/sched_ule.c. Verification against that source:
- Lines 2968–3009 sysctl_kern_sched_topology_spec_internal() produces hierarchical groups XML with cpu count, cpuset mask and optional flags HTT, THREAD and SMT.
- Lines 3017–3037 handle read-only sysctl XML. Lines 3096–3098 register SYSCTL_PROC(_kern_sched,...,topology_spec,CTLFLAG_RD) as the exact kern.sched.topology_spec OID, when SMP and ULE are built. Sony can omit the handler. An unprivileged userland application CANNOT install the kernel sysctl.
- releng/11.4/sys/sys/smp.h lines 103–105 set CG_FLAG_HTT=1, CG_FLAG_SMT=2, CG_FLAG_THREAD=HTT|SMT. Real HTT sibling groups need to be recognized; THREAD alone is ambiguous and MUST NOT be used as physical proof.
- releng/11.4/sys/kern/kern_cpuset.c lines 636–651 print cpuset mask LOW unsigned-long word first with comma-separated higher words. On PS5 64-bit, only the first 64 bits fit the probe's mask. Reject unexpected nonzero high bits rather than misidentify physical sibling groups.

R379 ps5_cpu_topology.h parser now accepts either HTT or SMT flags, but NOT THREAD-only. Full allowed 13 logical CPUs must be classified into 5–8 nonoverlapping physical sibling groups of at most two. The parser rejects broken masks and publishes core IDs only if ALL groups validate, so malformed later groups cannot leak partially valid hardware maps. The two probes remain read-only: kern.sched.topology_spec and kern.sched.ule.topology_spec. Startup EDEN_PS5_CPU_OS_TOPOLOGY now prints legacy_errno and ule_errno, retaining existing fields.

ASan/UBSan tools/check-ps5-freebsd11-ule-topology.py tests real FreeBSD XML HTT, SMT, mixed, THREAD-only, overlapping/partial masks, nonzero upper CPU words. The full source-extracted CheckWorkerTopology host fixture tests the HTT variant and CPU affinity. The actual firmware 13.60 may expose NEITHER read-only sysctl. When so, leave physical core separation unknown rather than fabricate it.

This is a source-proven parser bug fix, NOT a proven FC27 FPS or freeze solution. No additional PS5 test requested until native CI succeeds.

## R381 — Guard queued GPU draws against failed graphics pipeline build

R378 fixed the infinite-wait potential from missed Vulkan pipeline-builder completion. The existing graphics VkBindPipeline callback already skipped a null native pipeline after a failed build, but the later Draw / DrawIndirect callbacks did NOT check and could send vkCmdDraw* with an unbound or stale previous pipeline. This is a source-demonstrated command correctness risk, NOT proof of the R370 observed freeze or pixellated HUD cause.

R381 adds GraphicsPipeline::CanExecuteDraw(), which uses release/acquire ordering on the asynchronous builder's is_built flag before checking the published native pipeline handle. All four queued draw recording variants (ordinary Draw, indirect byte-count, indirect count, normal indirect) capture the prepared pipeline and return before issuing any vkCmdDraw* when that exact pipeline is absent, unfinished or failed. Failed cases increment the existing WorkerPipelineFailed diagnostic. The scheduler's build wait callback is queued BEFORE the draw callbacks; a pipeline that is still building is not skipped prematurely.

No change to cache locks, textures, descriptors, fencing, normal Vulkan commands or guest CPU memory invalidations. The source-extracted C++20 ASan/UBSan regression check-ps5-gpu-worker-draw-guard.py checks all four sites and a successful concurrent builder; pinned-source generator remains byte-equivalent for all 40 files. This is a correctness fix, not a demonstrated FPS improvement. Native and real-console tests still required.
