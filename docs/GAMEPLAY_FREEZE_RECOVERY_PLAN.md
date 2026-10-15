# Native gameplay stalls and saved-controller settings — recovery plan

Status: **open, hardware regressions reproduced on 13 October 2026**. The host CI and successful package build do **not** demonstrate runtime correctness. Active branch: `dev/ps5-sparse-jit`.

## Ground truth

The supplied screenshot shows that the **guest game itself** has its Classic control profile and editable action assignments. The user intentionally pressed Touchpad + Square **because those saved in-game assignments were not being honored**; the manual toggle did not originate or explain the original fault. Do not confuse button art (glyph textures) with the guest application's control configuration.

The captured session reports: `EDEN_PAD_MAPPING_CONTEXT mode=dual_manual menu_a=0 menu_b=1 match_a=1 match_b=0`, followed later by manual `EDEN_PAD_GAMEPLAY_PROFILE` toggles. The emulator altered guest A/B meanings during the same title session. R457's dual-profile route therefore interfered with any reliable test of game-owned input assignments. Its removal in source is a prerequisite, **not proof** that the guest save/apply path works. The next qualified package must confirm both the guest HID route and the game's settings persistence; no more controller scene heuristics.

The October heap capture includes **136 five-second Vulkan frame windows**, often near 30 FPS but with a minimum interval average around 7.1 FPS and a maximum single frame around 2,024 ms. There are prolonged ~20–22 FPS intervals in addition to isolated >1-second spikes. Late-session GPU/guest cache lock contention and guest IPC wait are nonzero despite very low JIT compilation in some windows. Cache purging alone cannot explain or fix all of this.

Some previous logs also display a `EDEN_GPU_REPORT_STALLED` immediately after opening a new title, containing older cumulative GPU counts. Verify whether this is inter-title stale heartbeat state before using it as proof of an ongoing 619-second hang.

The experimental worker placement on this firmware uses thirteen authorized logical CPU identifiers but no verified SMT siblings: five logical worker owners and three secondary logical CPU IDs (`0x1003`). Treat this as a **hypothesis under test**, not proven optimal placement.

## P0 — Restore ownership of guest controller actions

**In source:** one global/per-title physical-to-guest mapping resolved before the emulated HID device opens, then held constant throughout match, pause, transitions, and cinematic segments. The guest application alone interprets guest A/B/X/Y into shooting, passing, etc. The manual scene-toggle path and its match-specific mapping have been removed. Preserve per-title *launcher* mappings and the existing general launcher navigation. Do not edit guest save data or replace artwork to solve input semantics.

**Next verification:** compare the physical button → guest virtual button route with the four entries shown in the in-game settings, reenter gameplay after saving, reopen the menu and verify settings still persist after a title relaunch. If guest virtual inputs are stable but actions still revert, trace guest configuration/storage and the title's input selection rather than adding another emulator button-swap. Distinguish "settings displayed", "settings written" and "settings consumed by gameplay".

## P1 — Pinpoint the freeze at the pause/settings transition

Correlate timestamped frame spikes with: guest CPU phase and PC/blocked syscall; HLE IPC service and individual call latency; queue dequeue and GPU fence wait; Vulkan shader/pipeline work; texture/buffer cache lock **wait and hold time per owner**; save/configuration filesystem I/O; pause/resume and background-to-foreground applet transitions.

Instrument only the first stall and a short bounded before/after window, plus one event on a 100/200/500 ms frame; do not add verbose per-frame logging on the critical path. Use the existing independent heartbeat, which still operates if the main GPU report thread stalls. Reset inter-title progress timestamps before each new title so stale counts cannot masquerade as a live freeze. A continued 30 FPS indicator must not be treated as proof of guest CPU/input responsiveness.

**Decision tree:** if guest CPU is blocked in a save/profile IPC call, fix that service; if GPU thread is blocked in cache lock or fence, repair ordering and eliminate hold-across-wait; if both progress but pause HUD is corrupted, follow descriptor/renderpass/dirty-resource lineage; if GPU owner is idle waiting for guest work, do not optimize GPU utilization blindly.

## P2 — Remove unjustified CPU worker bottlenecks safely

Compare current `0x1003` secondary mask against a **non-pinned allowed-CPU** reference; keep normal process affinity and the firmware's scheduler as the control. The verified physical-topology path can retain affinity if readback confirms its masks. A logical-only mapping must never be advertised as SMT proof, and no policy should reserve hypothetical siblings by default without a measured benefit.

Require identical in-game resolution, duration and scene for comparisons. Compare p50/p95/p99 frame time, >100/>500 ms spikes, per-worker runnable/blocked states, shader preparation and cache-lock wait. Adopt a policy only after it improves tail latency without input freezes or GPU regressions.

## P3 — Repair HUD and graphics state independently

Reproduce the HUD defect in a stable static scene and through the pause/settings overlay. Correlate expected texture/render-target updates with guest writes, cache invalidations, descriptor bindings, pipeline compilation and draw ordering. The tracked draw-rejection counters at zero exclude only those rejection classes; they do not prove texture correctness. A game-specific graphic-pack absence affects glyph appearance but does **not** explain saved gameplay commands.

## P4 — Resource/contention audit

Distinguish virtual JIT reservation from committed native physical memory. Inspect the top HLE IPC services at the freeze and avoid synchronous flush/invalidate or expensive trace formatting under a GPU cache lock. Capture heap and direct-memory high-water marks once around the pause transition; do not change JIT capacity or memory budgets based solely on reserved virtual bytes.

## Acceptance gates

1. Source and host regressions pass without bypassing assertions, including one stable controller mapping and no manual match/pause mapper.
2. Native compilation, packaging, static integrity, and verified Git-derived launcher version all pass.
3. Hardware test: saved in-game action bindings work in a match, remain intact in pause/cinematics, and persist after restart — without a shortcut.
4. Pause/settings overlay can be opened/closed repeatedly without a freeze or corrupted HUD, and the input heartbeat and guest GPU/CPU progress remain live.
5. A representative 15–20-minute match has no >500 ms stall, no sustained sub-25 FPS collapse, and p95/p99 frametimes demonstrably improve versus the provided R457 baseline. Report measured numbers; do not claim success from compilation alone.

**Release rule:** do not label the gameplay issue fixed before these hardware gates are passed.

## Consolidated native qualification requested — 13 October 2026

Source-only gate **passed** at [run 38448896105](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38448896105) for commit `4bd32156cc92fc1db240980a10f6d677980fffd8`. The matching native job was skipped by design: no prior build of this remediation is evidence of hardware success.

The consolidated candidate includes three distinct source changes:

- **Guest-owned actions:** one immutable per-title physical-to-guest button mapping throughout gameplay and menus; no manual or automatic A/B scene toggle. This removes an emulator-induced contradiction, but saved game action behavior is not yet demonstrated on hardware.
- **Unverified topology:** do not constrain graphics and HLE secondary workers to `0x1003` or pin guest threads to presumed SMT siblings. Retain the operating system's allowed logical CPU set until physical topology is verified. This is a correctness-first scheduler baseline, not a demonstrated FPS gain.
- **Liveness diagnostics:** reset progress age at each title transition; previous `EDEN_GPU_REPORT_STALLED age_ms=619430` may include old-title counters and cannot by itself diagnose a new title's pause stall.

**Pause-freeze remains open:** the older pause investigation observed continued render/present activity near 30 FPS while the game UI stopped responding; later tests contain stalls up to 2,024 ms and sustained low frame windows. Do not conflate FPS with guest CPU or input progress. If a future build reproduces the pause freeze, correlate guest HID fullkey publication, guest IPC thread waits, cache lock hold/wait owners, CPU phase/PC, and GPU progress around the first event rather than tuning shaders or JIT by guesswork.

**One build, not one more speculative console cycle:** request native All-On preflight, compile and packaging on the already-green source snapshot. Do not mark mapping, performance, HUD or pause freeze fixed until the acceptance gates above succeed on hardware. Keep prior captures for comparison; do not insist on clearing shader caches between comparable runs.

## Reference-repository integration — 13 October 2026

The host regression pass for the new source candidate is green ([source preflight 38459874332](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38459874332)). Two recent native-console lessons have now been compared against the actual port, not blindly copied:

- **CPU scheduling:** native game titles normally expose 13 logical CPUs while the process may create more runnable FIFO threads. In **All-On development builds only**, the first per-thread scheduler probe now attempts to replace FIFO priority 700 with round-robin priority 700, preserves the OS affinity, and reads the result back. The GPU owner, emulated CPU workers, Vulkan compiler threads, and pad input worker are covered by their existing worker-entry hooks. Failed changes remain at the original policy. Normal release builds make no scheduling change. A hardware log with `rr_verified=1` proves the kernel accepted a change, not that FPS or responsiveness improved.
- **Texture collection and persistent shader cache:** recent reference-source fixes for bounded texture eviction scanning and native shader-cache access were already carried by this fork. Do not duplicate them, rebalance the texture budget blindly, or port a foreign graphics API's memory rules into the guest renderer.
- **Pad handling:** batched native input samples, one signed-in user's pad handle, and a stable game-session guest mapping are already in place. The launcher-specific JSON mapping read/write discrepancy is addressed separately. Nothing here asserts that a guest game's own saved action bindings are read or applied correctly.
- **Interpolation:** optical-flow presentation intentionally remains outside this freeze recovery. It adds image latency and cannot repair an emulated guest paused in IPC or a blocked GPU queue.

**One hardware qualification:** compare the same scene and existing cache against the prior R457 capture. Verify the native scheduler result (`original_policy`, `rr_attempted`, `rr_error`, `rr_verified`) first, then actual guest HID receipt and saved game actions, repeated pause/resume with visible HUD, >100/500 ms stalls and 5-second GPU/IPC/cache windows. Require no new starvation, controller dropouts or command misinterpretation. Keep the candidate experimental if its scheduler outcome or frametimes are worse than the earlier baseline.

## Native FTP qualification: c3774d3e, 13 October 2026

Evidence: native build `c3774d3e8efbaa81c53ac3d2146848cc9b358cda`; read-only device FTP `/data/prosperoeden/logs/{boot-trace.txt,stderr.log,heap.log,stderr.prev.log,heap.prev.log}`, collected after the unsuccessful title test. **User-visible test result: failed** (match entry freeze/stall, unchanged subjective lags and saved match-button behaviour). Do not classify this release as a gameplay fix merely because CI passed.

- The executable provenance in `boot-trace.txt` matches the source SHA exactly. No ambiguity about which native candidate was launched.
- The native OS accepted the experimental scheduling policy: CPU owners, GPU owner, pad input, renderer workers changed from `SCHED_FIFO(1)` to `SCHED_RR(3)` at **unchanged priority 700**, with `rr_error=0 rr_verified=1` and full `allowed_mask=0x1fff`. The Vulkan pool reports six compiler workers over 13 permitted CPUs versus one worker confined by the old guessed `0x1003` affinity. These are policy/placement proofs, **not FPS or crash fixes**.
- The GPU-owner's final five-second Vulkan report is **frame 9480**, `fps=30.000`, `worst_ms=37.983`, `gpu_idle_ms=3963.297`, `gpu_dispatch_ms=1058.050`, `guest_ipc_ms=1045.556`, `guest_dequeue_ms=451.660` and `jit_ms=64.872`. The guest 30 FPS ceiling alone does not identify the reported gameplay lag. Last full GPU report: **no allocation failure** and `largest_last_confirmed=2032140288`.
- The independent pad-input monitor then observes `EDEN_GPU_REPORT_STALLED` repeatedly: `frame=9480 gpu_ticks=9514 draws=4008660` unchanged as `age_ms` grows from 24059 to at least **240430**. In the same interval, `guest_ipc` grows from 509395 to 672710 and controller sampling plus Fullkey Npad writes continue, with zero reported pad read errors/interception. The game process/guest services are still partially active: this is a **persistent render/GPU-owner progress stop**, not a logged native signal crash.
- There is no `EDEN_CRASH_REPORT after_crash=1`, explicit memory-allocation failure, or a fatal GPU exception in these session files. Do not infer the precise blocked native function from counters alone. `dma_active_ms=0 puller_active_ms=0` only rules out *those two instrumented wait spans*; it does not prove the GPU thread is not blocked somewhere else.
- `EDEN_PAD_MAPPING_FIXED ... layout=0 a=0 b=1 x=2 y=3 title_override=1 own_mapping=0`. The previous title-mapping JSON round-trip fix does **not apply to this game's session**; it therefore cannot explain the user's in-game saved action-binding failure. Physical input reaches the emulated Fullkey Npad LIFO, but consumption and guest save/config action resolution remain unproven.

**Next engineering gates, not another blind hardware trial:** (1) capture the **actual blocked native GPU owner PC/call site at first detected sustained stall**, using bounded diagnostics isolated from render/cache locks, rather than increasing worker counts again; (2) correlate guest synchronization/IPC with last GPU tick, and verify if the owner is waiting on a queue, a host fence, or a guest HLE event; (3) trace guest save/config reads and title selection for persisted match action bindings (leave the launcher/guest HID physical mapping unchanged); (4) only after a causally supported fix, run a single full native validation against the previous captured scenario. Do not reclassify 30 FPS stability before the stall as a recovered match.

## Host-simulated candidate review after the failed c3774d3e test

The active shipping backport **already** contains a broadcast dequeue epoch in `vendor/encore-active/eden-backports/src/core/hle/service/nvnflinger/buffer_queue_core.{cpp,h}`. Direct changes to the pristine vendored source were restored. The proposed native `PresentLater` wakeup was also **reverted**, because exact-source host state enumeration found it cannot improve the relevant path: once `AcquireBuffer` drops an older queued frame, the newly selected frame is already timestamp-eligible. Across **333,333 C++ scenarios** (0-5 frames, all short timestamp/auto combinations, three deadlines), **37,778** deferred presentations and **295,552** accepted presentations produced **zero** difference between the original and the proposed patch. No release or console test should be justified by that dead branch. The 2026-10-13 All-On build `b48465dd` was cancelled, and its artifacts must not be treated as candidates.

`tools/check-ps5-buffer-presentation-state-space.py` now compiles the **actual pinned upstream function body**, compares its externally visible queue/slot behavior to the rejected hypothetical patch, and fails if someone tries to reintroduce that patch. `tools/check-ps5-buffer-dequeue-generation.py` separately compiles the **active** shipping broadcast implementation under 400 host waits. Both are source-specific simulators, **not console execution**. No new log output is added to the emulator.

The remaining candidate code change is removal of a periodic blocking `fflush(stdout)` from the Vulkan presentation callback; the independent log-pipe drain and the first-frame startup flush remain intact. This is an isolated potential latency improvement, **not a proven 240s hang or FC27 action-mapping fix**. The saved title profiles remain unchanged. Require a causal diagnosis before another hardware trial.


## Broad Mac host simulation audit — 13 October 2026

Target: **only** `dev/ps5-sparse-jit`. An isolated, clean, partial Git checkout was expanded on the authorized ARM Mac to include all locally needed shipped sources/dependencies (about 4.1 GiB). Original source snapshot `859a71c6`, final test-only/CI snapshot `6c3425ca`. No device filesystem, title save, ROM or console setting was changed. The earlier [source-only CI 38470897244](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38470897244) passed for `859a71c6`; that does **not** prove console behaviour.

- Executed **253 historical/current host test commands**: 158 gathered from the source preflight workflow plus 95 additional check scripts. Mac toolchain: Python 3.14, vendored header include roots (154 include directories), ARM clang/SDK, isolated image library. **225 passed** across the broad sweep plus individually re-run missing-header/toolchain and updated-source checks. The aggregate count is not a claim that all 253 passed in one uninterrupted run on a single SHA: 217 passed in the full dependency-qualified run, six previously blocked source replays passed with the actual vendored Boost/JSON include roots, and two previously failing historical replays passed with updated source/test compiler settings.
- **19 not executed meaningfully**: require `.local/headless-cache`, a native build directory or an explicit input file not provided to their CLI. Do not reinterpret the resulting exceptions as runtime failures.
- **Four external-tool blocked**: optional `astcenc` encoder missing; concern optional texture/glyph packaging, **not** physical gamepad action mapping.
- **Five native Linux/x86 fixture incompatibilities on ARM macOS**: x86 pause builtin, C11 threading header, Linux fixed-map/memfd constants, and Linux `mincore` ABI (two fixtures). Run these with the existing Linux source CI or dedicated Linux host build, never claim they ran on this Mac.
- Other representative verified paths: guest buffer dequeue broadcast under 400 competing waits; 333,333 exhaustive true-C++ guest presentation states identifying and reverting a *no-effect* candidate; Vulkan queue worker and stop-aware producer with 8,096 + 24,576 commands and repeated stop/cancel cycles; 1,000 × 40 texture readback entries under address/undefined sanitizers; 32 MiB batch/readback + fence-order edge cases; shader worker placement source gates; sparse VA lifetime; title mapping precedence, pad/HID pause edges, controller art/source provenance; renderer five-second frame windows including a six-second stall; watchdog reporting without false inactive-title alerts.
- Three independent historical test/data inconsistencies were repaired **without any game-path changes**: controller icon opacity/position assertions updated to match existing authored UI; cross-platform research engine/transfer bounds expanded to pass the strict source schema without claiming asset parity; release matrix validator now accepts exact mixed-case IDs that its own inventory defines, while still reporting **0/26 hardware approval proofs**.
- A previously unrun frame-window source replay was made self-contained and promoted into CI; controller-art and evidence/source-index checks were also added to host preflight so they cannot become stale again. **No game-controller action-override fix, GPU stall root-cause fix, or measured FPS improvement is claimed here.**

**Next work gate:** no additional console test justified by this broad source-only pass. Use the already captured failed native session to isolate the actual GPU/guest progress dependency and investigate the title's own saved action-selection path. Only schedule a single new hardware comparison after a reproducible, causal fix exists, with the unchanged existing cache and same test scene. In particular, an accepted scheduler policy and a smooth-looking 30 FPS window before the hang are not evidence that the pause/freeze or gameplay controls are repaired.

## Recorded-workload stress qualification — 13 October 2026

The 13.60 console's existing `heap.log` and `stderr.log` were collected **read-only** via the user-authorized Mac's FTP access; only de-identified numerical samples were committed as `tools/fixtures/native-load-20261013.json`. No original device log, network address, user file or game save is stored in the public repository. The recorder confirms baseline native build prefix `c3774d3e`.

**Actual production trace, not an assumed load:** 68 consecutive 5-second windows, **9,479** window-counted frames across 341.505 seconds; the lifetime frame counter at last successful report is **9,480**. Median window reports near 30 FPS but there are early drops as low as 20.334 FPS; worst observed frame interval is **575.264 ms**, with **two** frames exceeding 500 ms. Across window *maxima*, p95 is about 306 ms; **this is not a p95 per-frame frametime**. GPU owner median 5-second counters are `gpu_idle_ms=3943` and `gpu_dispatch_ms=1055`; the owner did not display sustained capacity saturation in the pre-freeze windows. The last 10 windows are back at approximately 30 FPS, and the final period has `gpu_fence_ms=3.514`, `jit_ms=64.872`, `cache_wait_ms=10.439`; none directly identifies the **subsequent** infinite wait.

There are **55** independent `EDEN_GPU_REPORT_STALLED` samples, from `age_ms=24059` to `1693230`. During the **1,669.171-second interval between observations**, GPU progress remains fixed (`frame=9480`, `gpu_ticks=9514`, `draws=4008660`, `guest_writes=3123456`, `guest_reads=64669`, `guest_dequeues=9515`, `cache_collisions=347236`), while IPC rises by **1,259,768** = approximately **754.7 calls/second**. Input sampling/heartbeats continue without reported read errors. Thus host console evidence is a **sustained GPU/guest production progress stop with independently surviving threads**, not proof of an allocation failure or generalized 100% GPU saturation. The 28-minute reported age is an observed minimum; it must not be attributed to a specific blocked call without a call-site capture.

**Exact source-backed stress simulations**, `tools/check-ps5-native-load-replay.py`:

- Loads the recorded 68-window workload and all 55 stall snapshots and rejects altered order, window/frame totals or advancing GPU counters during the observed hang.
- Reuses the **actual C++ native stop-aware SPSC enqueue method** from `headless/gpu_queue_stop_wait.inc`, with the same queue mock as `tools/check-ps5-gpu-producer-wake.py`. Drives 9,479 / 37,916 / 75,832 synthetic command units for **1×/4×/8×** load, respectively, as well as 4,008,660 / 16,034,640 / 32,069,280 draw-like operations and 3,123,456 / 12,493,824 / 24,987,648 guest-write-like operations. Concurrent synthetic IPC work uses 509,395 / 2,037,580 / 4,075,160 prefreeze operations. It asserts bounded 32-slot backpressure, loss-free FIFO and successful completion after every load.
- A separately injected **virtual freeze** holds the producer against a full queue while 1,259,768 synthetic IPC operations and 497,500 pad polls proceed, then asserts cancellation unblocks the producer and empties the queue cleanly. This can reproduce the coarse observed liveness *signature*, not the cause of the freeze. Do not claim it ran 1,669 seconds in real time or that a queue element is an actual hardware draw.
- Both normal and AddressSanitizer/UBSan executions **passed on macOS ARM**. The test is included in Linux source preflight and in the native All-On prebuild gate; this says nothing yet about final run results or the firmware/GPU driver.

**Triaged interpretation:** The tested enqueue primitive survives 8× synthetic throughput and safely releases waits on cancellation. This lowers the priority of a simple queue-capacity/wakeup bug. The earlier latency spikes have a variable profile (high JIT in some windows, high IPC elsewhere), so do not tune only one cache or worker count by intuition. The **persistent 28-minute freeze** requires an actual owner/producer/consumer call-site diagnosis; an active IPC loop alongside zero frame progress is consistent with a blocked GPU owner **or** a guest producer that has stopped submitting, and neither can be distinguished using this one set of counters. No gameplay binding error is solved by the queue tests. No new console build is justified by a stress-test-only change.

### Recorded five-second timing and bounded-queue model

`tools/check-ps5-native-timing-replay.py` is a second, deliberately optimistic **virtual-time** model using the 68 recorded window durations, actual per-window GPU dispatch sums and actual counts of presented frames. It distributes GPU owner dispatch time uniformly across modeled frame-sized workload units; this is an explicit modeling assumption because source logs do not include each native queue insertion and completion timestamp. With the 32-slot queue held fixed, the baseline 1× load reaches modeled occupancy **1**, and adding one hypothetically GPU-owned pause as long as each window's recorded worst interval (up to **575.264 ms**) reaches occupancy **13**. Neither baseline hypothesis fills the queue. Holding the same modeled service throughput at **4×** and **8×** arrivals fills its capacity (19,058 and 74,720 modeled backpressure events respectively): 32-slot capacity and stop-aware waits are *necessary*, but resizing the queue is not a data-supported fix for observed normal-rate 500 ms stutters.

At zero GPU completion and a hypothetical still-running producer issuing 30 workload units/s, 32 entries would be filled in **1.067 seconds**, far sooner than the measured 1,693.230-second report age; other guest activity can continue meanwhile. **This does not establish whether the actual producer continued attempting submission**, nor whether the GPU owner was itself blocked in a command, a fence, Vulkan presentation, or the detailed profiler. The queue stress, virtual timing replay and real telemetry must remain three distinguishable evidence levels.

Risk matrix for next causal repair: (1) classify the GPU-owner's last real work boundary and producer submission state at initial stall; (2) for transient spikes, compare guest JIT and IPC activity with native per-window delay without mistaking cumulative thread-nanoseconds for serial frame time; (3) keep the game-owned action preferences as an unrelated guest-save/action-resolution problem. **No additional logging flood, queue-capacity change, or blanket thread-priority adjustment is warranted by this source-only replay.**


### 30-FPS-stable gameplay hitches: compositor FPS is not frame freshness

The user reports frequent in-match lag, HUD stutter and delayed gameplay despite **30 FPS remaining stable**. This must **NOT** be conflated with the 500–575 ms presentation gaps during other time windows, or the later full freeze. A post-hoc review of the 68 captured five-second windows finds **36 windows at 29.95–30.05 FPS with worst callback interval below 38 ms** and **all 10 immediately before the prolonged freeze** at approximately 30 FPS with worst callback gap 33.7–38.0 ms.

**Source-level scope error in prior interpretation:** `GraphicsWindow::OnFrameDisplayed()` increments `frame_total` and estimates FPS from end-of-`RendererVulkan::Composite()` callback intervals. On the native Vulkan path the callback is in `SCOPE_EXIT` *after* `present_manager.Present(frame)`; `PresentManager::Present` queues the render frame through `scheduler.Record()` when `async_presentation` is enabled. Native launcher sets `async_presentation = true` for Vulkan; `PresentThread` later performs `CopyToSwapchain`, and the Vulkan present queue is even further downstream. Thus a steady 30 compositor callbacks/s cannot prove a steady 30 actual scanouts/s, stable presentation latency, absence of identical pixel contents, smooth gameplay simulation advancement, or immediate response to controller input. A simulated 120 ms presentation-worker pause **after** the callback is deliberately invisible to this FPS metric.

Guest-side source is also relevant: `HardwareComposer::ComposeLocked` calls `nvdisp.Composite` only when `has_acquired_buffer` becomes true for a **new BufferItem**. Cached held buffers alone do not trigger the callback. Hence stable 30 FPS is useful evidence of new BufferItem acquisition at that cadence. **New BufferItem != new gameplay pose/state != actual TV scanout**. Existing `not_shown=0` also makes a skipped-frame explanation unsupported in this trace.

The 68 detailed source windows include `EDEN_PRESENT_WAIT_PHASE`: `GetRenderFrame` waits for a free present resource total about **0.07 ms per five-second window** (median across consecutive interval deltas) and its preceding completion fence about **0.30 ms** per five-second window; the 32-slot GPU-producer `gpu_full_ms` stays **0** in final normal-rate windows. These figures **argue against persistent** pool exhaustion as the usual source of 30-FPS-visible lag; they do **not** measure `vkQueuePresentKHR`-to-display or distinguish repeated scene content. Guest worker `cpu_ns` clocks were not available on this device trace, so do not infer sustained per-core utilization from them.

The `tools/check-ps5-display-vs-guest-fps.py` offline replay pins all relevant source contracts and uses **150 callbacks in 5 seconds**, projected onto a **60 Hz display**. Host Mac results:

| Deterministic model | Compositor callback FPS | Distinct displayed content states | Longest unchanged interval | p95 display age |
|---|---:|---:|---:|---:|
| Regular | 30.000 | 150 | 33.33 ms | 33.33 ms |
| Asynchronous present delayed 120 ms intermittently | 30.000 | 150 | 150 ms | 116.67 ms |
| Guest content repeated across otherwise newly acquired frames | 30.000 | 129 | 133.33 ms | 33.33 ms |

A model input just after frame 49 becomes visually observable after **49 ms** in the base case and **149 ms** when the guest's visual state repeats. These are deliberately synthetic clocks/frame identifiers; **they are not measured FC27 input lag or hardware pixel comparisons**.

**Pacing configuration caution:** the Vulkan swapchain implements explicit target-30 pacing, but the engine's default `frame_pacing_mode` is `Target_Auto`. The captured logs do not establish a forced target-30 setting; therefore do **not** claim double limiting or change pacing mode on that assumption. The asynchronous native presentation path is separately source-proven.\n\n**Revised diagnosis priority:** treat two classes as separate incidents. Persistent in-match judder while callback FPS is steady should prioritize the *guest gameplay simulation/action advancement* and *native downstream Vulkan presentation/scanout scheduling*, not keep increasing the GPU command ring, JIT cache or global thread priorities on intuition. The eventual 28-minute no-progress freeze is separately a genuine lack of upstream GPU/tick/frame progress. A single shutdown/stall fix would not automatically cure normal-rate animation judder. Until the guest-state/content identity or true display completion can be established causally, **do not claim a 30-FPS gameplay-hitch fix or request another trial**.


### Source-backed asynchronous presentation and submission-lock stress

**Hardware log facts, unchanged:** 36/68 windows show near-30.0 composite callbacks/s, with worst callback interval below 38 ms, and the last 10 windows are all near 30 FPS before all compositor/GPU counters stop. Native monitor reports a 60 Hz output; most interval histogram counts are the 20–36 ms bucket. No skipped frames were reported. The `EDEN_PRESENT_WAIT_PHASE` total five-second free-buffer-wait and present-frame-fence-wait deltas are tiny in these windows (~0.07 ms and ~0.30 ms), meaning **pool exhaustion was not sustained during the last healthy callbacks**. These counters **do not** observe actual `vkQueuePresentKHR` latency, the display scanout clock, per-buffer scene freshness, or gameplay action advancement.

**Actual compiled C++ source replay:** `tools/check-ps5-async-present-source-stress.py` extracts and compiles the active `PresentManager::GetRenderFrame`, `Present`, `WaitPresent` and `PresentThread` bodies. A host mock scheduler immediately executes the scheduler-record lambda (optimistic), fake fences are nonblocking, and a fake Vulkan present operation injects specified latency. Critically, the native `MAX_FRAMES_IN_FLIGHT=7` is an **upper bound only**. The actual frame pool is `min(swapchain.GetImageCount(), 7)`; the swapchain ordinarily **requests three images**, and the *returned* count is not established by the captured console logs. Accordingly, run both 3- and 7-image pools, not just 7.

| Host scenario (150 callbacks, ~30 FPS) | Maximum callback interval | Maximum downstream present interval | Maximum callback-to-present age |
|---|---:|---:|---:|
| 3 present frames, 2 ms nominal | 38.22 ms | 38.22 ms | 5.30 ms |
| **3 present frames, 130 ms intermittent** | **68.37 ms** | 164.42 ms | 132.21 ms |
| **7 present frames, 130 ms intermittent** | **38.38 ms** | 165.82 ms | 135.05 ms |
| 7 present frames, 350 ms intermittent | 152.06 ms | 383.90 ms | 355.07 ms |

Every scenario completed with all 150 frames delivered. The latency thresholds above were checked on the authorized Mac with `EDEN_PRESENT_STRICT_HOST_TIMING=1 python3 -B tools/check-ps5-async-present-source-stress.py`. CI repeats the source-derived lifetime/concurrency run but deliberately does **not** enforce strict wall-clock maxima on shared, potentially overloaded runners; a clean CI run alone cannot validate the 30-FPS timing observations. **This reverses an overbroad earlier conclusion:** a 130 ms present delay can be hidden in the compositor's 30 FPS **when the presentation pool is sufficiently deep**, but **not necessarily when the driver provides only three images**. For the user's final 10 windows (worst compositor callback under 38 ms), repeated 130 ms WSI stalls are a poorer fit if the runtime pool is indeed three. The alternate hypothesis of **new framebuffer buffers carrying stalled/repeated guest animation states** remains viable and is not measurable in current logs. Do not pretend that any Mac simulation establishes the real PS5 image count, game pose updates or scanout cadence.

**Concrete contention dependency:** `Swapchain::Present()` holds `scheduler.submit_mutex` around the actual `present_queue.Present(present_info)` Vulkan call. `Scheduler::SubmitExecution()` takes the *same mutex* around `master_semaphore->SubmitQueue()` on the GPU worker. `tools/check-ps5-vulkan-present-submit-contention.py` anchors both source sites and runs host stand-ins: synthetic presentation holds of **5/130/350 ms** delayed concurrent GPU submission by **5.28/133.39/350.16 ms**, while independent IPC continued. A genuine blocking WSI present could thus couple visible lag to GPU submission pressure, and a driver-side nonreturn could potentially propagate to the prolonged stop. Importantly, this is **a conditional causality model, not evidence that the PS5 WSI driver actually held the lock for 130 ms**.

**Mandatory synchronization warning:** Device setup requests only one Vulkan queue per family and can choose the same family for graphics and present. When the queue handles are identical, Vulkan requires external synchronization of queue use. Removing `submit_mutex` unconditionally is *not a safe fix*. Separately, `Swapchain::AcquireNextImage()` uses `UINT64_MAX` timeout; this is a different potentially indefinite **present-thread** wait that happens *outside* the submit mutex, and can also produce free-pool backpressure. The retrieved native trace cannot distinguish these paths. Never attribute the freeze specifically to the shared lock or the unlimited image acquisition without causal evidence.

**Intervention gate:** do not add per-frame logs or change FIFO vs MAILBOX, timeout handling, priority or queue locking from these host tests alone. The next native change should be a narrowly proved correction with a source-derived preservation test for queue ownership/fence/semaphore order and a rollback contract; no new FC27 console trial from this audit alone.


### First native corrections from source-backed WSI audit

The stress tests make **two Vulkan image-acquisition correctness faults** provable without extrapolating from FPS: (1) when `vkAcquireNextImageKHR` returns `VK_ERROR_OUT_OF_DATE_KHR`, no valid image index exists, yet the original implementation fell through into `resource_ticks[image_index]` pacing and tick tracking; (2) when it returns `VK_SUBOPTIMAL_KHR`, the acquisition is successful and signals the image-available semaphore, but the original function returned "recreate now" before the acquired image/semaphore was consumed.

Native fix, applied **only** to the generated `vulkan_swapchain.cpp` through `tools/prepare-vulkan-port.py`, not by modifying immutable vendored snapshots:
- `VK_ERROR_OUT_OF_DATE_KHR`: mark outdated and **return immediately**. Caller uses its existing maximum-three-attempt swapchain recreation path, never an invalid image index.
- `VK_SUBOPTIMAL_KHR`: acquire/present the **valid** current image, allowing its semaphore to be consumed. Preserve the `is_suboptimal` flag; the next `CopyToSwapchainImpl` sees `NeedsRecreation()` and rebuilds the swapchain then, not while the acquired image is unconsumed.
- Native-only `vkAcquireNextImageKHR` waits are changed from `UINT64_MAX` to **40 successive 250ms timeouts (10 seconds total nominal)**. A `VK_TIMEOUT` or `VK_NOT_READY` return is retried without touching image index, resource tick or semaphore state. After 40 exhausted slices throw `vk::Exception(VK_TIMEOUT)`, handled by existing `PresentThread` exception publication and launcher recovery path. This is **bounded failure instead of indefinite wait**, not a hang cure if the underlying driver ignores the timeout; and after a genuine >10-second stall the game will exit via existing failure handling rather than resume.
- All ordinary acquisition success, non-native behavior, fatal surface-loss propagation, queue synchronization and semaphore requirements stay unchanged. The shared `scheduler.submit_mutex` is preserved for identical VkQueue handles. This change does not invent a game animation fix, bypass GPU fences or alter saved game controls.
- `tools/check-ps5-native-acquire-failfast.py` replays **the exact patched body compiled in C++20**, including transient timeout recovery, a run of 40 consecutive timeouts, a no-image/outdated index sentinel, a valid suboptimal image and fatal error propagation. This passes in both native-macro and non-native mode on the authorized Mac. Linux host preflight and native build gate now run the same validation.

**Important validation limit:** A source-level memory/synchronization bug has been corrected; current PS5 telemetry cannot tell whether these two WSI statuses occurred during the recorded 30-FPS hitches. No observed console FPS gain or reduced input lag is claimed. Qualify native build first, then one controlled device comparison only when the code is compiled and ready.

Native qualification gate: compile this exact patched generated swapchain with the All-On native toolchain before claiming it is ready for console validation. The source test only proves the modeled VkResult/error branches; it cannot simulate a WSI driver that ignores Vulkan timeouts.


## Native guest fault — 15 October 2026 (00:45 capture)

The user-supplied capture `boot-trace(20261015-004550).txt`,
`stderr(20261015-004554).log` and `heap(20261015-004550).log`
belongs to tested source `9d066b826cf277efda1f0ea9d5555de18e2f5b08`,
firmware `0x13600007`, title `0100C49025D3E000`.
This is a **specific guest instruction-prefetch fault**, unlike earlier
sessions with a persistent 30-FPS overlay and a stalled GPU-owner heartbeat:

```text
guest thread Job0 tid=90 pc=0x4 lr=0x8b9f42cc
sp=0x10bb46d700 fp=0x10bb46d700 jumped to an unmapped address
```

The guest-fault path also emitted `EDEN_STAGE phase=guest_fault` and
returned to the launcher, not a native signal handler. The heap sample at
the fault reported `failures=0`, `live_bytes=2636901564`, and
`peak_bytes=2856496319`; JIT sparse reservations/commitment were released
during shutdown. None of these observations proves an out-of-memory cause
or JIT corruption. The near-null target `0x4` is consistent with a bad
guest indirect-branch destination, but the saved LR alone cannot identify
who produced it. Do not patch the fault handler to silently continue or
suppress the exception.

Before attempting a correction to guest JIT/HLE, resolve the saved LR
against loaded guest executable segment ranges, and record on the *fault
path only* the instruction/branch source and the relevant register value,
using safe guest-address validation before any memory read. Preserve
the exact tested build/source SHA; compare with a native A/B run only after
a hypothesis-specific host regression exists. Existing 5-second frame
pressure probes report mostly zero for several wait categories; those
zeros cannot be treated as proof that no thread was blocked.


## Cross-check of 01:22 archive — 15 October 2026

The later-collected filenames `boot-trace(20261015-012240).txt`,
`stderr(20261015-012244).log`, `heap(20261015-012240).log`,
and `network-accepted(9).log` preserve **the same tested session**
`9d066b826cf277efda1f0ea9d5555de18e2f5b08`, not a second
independent post-fix crash. The session started at epoch
`1792024431032 ms` (2026-10-15 00:33:51 UTC). The sampled guest
fault at monotonic `136407283966809 ns` corresponds to approximately
00:44:47 UTC, around **656.1 s after session start**. The adjacent
launcher diagnostic confirms the original `pc=0x4`, `lr=0x8b9f42cc`
fault; `failures=0` in the heap snapshot is not evidence of
memory-corruption absence.

Offline numerical analysis of `heap(20261015-012240).log` found 127
five-second Vulkan frame windows: median **29.999 FPS**, minimum
**16.520 FPS**, maximum individual window-reported `worst_ms=721.319`,
25 recorded frames over 200 ms, and five over 500 ms. The retained
`heap.prev(20261015-012241).log` has 131 windows across earlier dense
JIT sessions: median **29.999 FPS**, minimum **18.087 FPS**, maximum
`worst_ms=1233.472`, 23 over 200 ms, six over 500 ms. The latter file
contains multiple sessions, so **this is not a controlled dense-vs-sparse
A/B**. Sparse JIT cannot be claimed to resolve stutter from this
comparison. `EDEN_FRAME_PRESSURE` outputs zero for all its categories
in many windows with visible spikes; no conclusion about actual
GPU/IPC/cache/JIT wait durations can be drawn from those zero values
until the instrumentation's enabled/observed path is verified.

The current-session portion of the timestamped network audit (starting
at the `session-start` marker for `9d066b82`) records 369 individually
logged denied guest DNS lookups and 213 aggregated denial summaries.
The network file is cumulative and also contains **older sessions**;
the denial records must not be counted as successful external
connections. The last network record is approximately 37 s before
the recorded fault. No network-to-crash causality is established.

This particular `9d066b82` launcher log reports a catalog of 4,835
retail-case index rows. Two installed titles produced name-based
matches; title `0100C49025D3E000` produced `status=no-match`
for the then-available scanned/alternate names. The successful
`EDEN_CASE_FETCH status=stored` records prove source downloads and
writes, **not** successful GL texture upload or on-screen rendering.
Later source changes added `EDEN_CASE_RESOLVE`,
`EDEN_CASE_RESULT`, and `EDEN_CASE_TEXTURE` stages and fixed the
native BGRA TGA cache validation; none were exercised by this
older tested binary. Do not classify the retail-case problem as
fixed without seeing those stages in a matching native artifact.

The independent pad input heartbeat increased from 1,250 polls /
4,022 returned samples to 157,500 polls / 425,885 samples over
approximately 647.80 s: about **241 poll calls/s** and **651 returned
samples/s**, or **2.70 samples/poll**. These are API-read/sample
counters, not unique human button actions. The sample flow continued
to within about 1.8 s of the guest fault, with `errors=0`; it does not
establish the title's own in-match action-binding correctness.

**Next engineering gate:** preserve the two distinct failures
(guest invalid branch versus indefinite GPU progress stall).
Resolve the saved guest LR against loaded code segment boundaries,
and only in the actual fault handler record safely validated
branch-source instruction/register context. For retail art, prove
index/name lookup, cached-file format, `box_art()` publication,
decode success, GL texture upload, and active face rendering in
separate stages. Do not request another console cycle merely to
repeat the already captured 01:22 archive.


## Native retail scans — host render evidence gate (15 October)

The 15 October launch/library media changes are deliberately distinct from
the native guest fault and GPU-stall investigations. A retail-case **file
download** is not a successful **visible texture**. The source now emits
these independently attributable stages:

- `EDEN_CASE_INDEX` / `EDEN_CASE_LOOKUP`: packaged physical-scan metadata,
  and exact/alternate title-name selection. An unknown game (not present in
  the index) must not reuse a different edition's retail art.
- `EDEN_CASE_FETCH` / `EDEN_CASE_RESOLVE`: accepted response, atomic
  BGRA TGA write, local full-length/header/dimension validation.
- `EDEN_CASE_TEXTURE`: decoded source dimensions and requested GL texture
  upload result. This is not itself visual proof of GPU sampling.
- `EDEN_CASE_DRAW`: once per front/back visible launch-face state,
  distinguishes `status=placeholder` from `status=ready`, and labels
  `source=retail` versus `source=fallback` rather than treating either as
  a genuine paper scan.

The worker's per-face `case_artwork_changed` mask only invalidates an
existing GL jacket after a successful replacement; unchanged sources keep
their resident textures. Simultaneous Home/Library fetches are serialized
on background workers; waiting checks cancellation every 50 ms so a
pending *second* request does not unnecessarily block launcher teardown.
The active network request's own cancellation/timeout is still a
separate boundary and is **not** proven by this lock policy.

Host-only regressions now exercise the actual C++ 32-bit BGRA case TGA
decoder, both vertical scan orientations, half-size pixel output, and
truncation rejection. The independent launcher OpenGL preview captures
front/back/spine poses and Library front/back/zoom with actual scanned
art and explicit fallback. Passing host screenshots qualifies the
renderer path on the host, **not** console graphics-driver behavior.

**Tomorrow's console gate (only after a green matching native build):**
record the tested git SHA and packaging run; check independent front/back
in the Library and in launch animation; preserve both
`EDEN_CASE_TEXTURE` and `EDEN_CASE_DRAW` lines if a face still displays
a placeholder. Do not clear every cache again or interpret a successful
preview as proof that game-mode JIT, HUD, GPU stalls, or a guest
`pc=0x4` fault has been repaired. The guest fault's code-range
provenance is logged once at title start under
`EDEN_GUEST_CODE_RANGE`; matching it with the saved LR is the next
evidence requirement before modifying JIT/HLE.


## Final All-On native candidate trigger (15 October)

Build `38667914391` compiled and validated the package at source
`15adbaafa2f6af387392db39ccd62258da039742`; a test-only
`Prospero.Eden-Encore-PS5-all-on-test` artifact was uploaded.
Its media-worker wait was subsequently improved at source
`5296e9ac`, with the source-level cancellation regression
at `10488e34`. The host preview at `38669015120` was
separately requested to validate rendered physical scans.

The final release candidate must compile the **later** tree
containing cancellation-aware serial fetches, precise face
invalidation, and launch-paper submission traces. This marker
triggers the independent native test profile; its success,
actual SHA, and artifact IDs must be checked before any
installation recommendation. No retroactive assertion that the
older binary contains these changes is valid.


## Fatal LR mapping and cancelled media fetch guard

After the initial full native candidate was scheduled, source validation found
one additional unfinished-transaction edge case: a cancelled retail-case
download could retain the five-minute rate-limit entry despite a premature
launcher transition. The cancellation path now clears that gate without
deleting already cached faces; a currently running network request still
remains bounded by its own cancellation support/timeout.

The fatal guest prefetch abort now issues exactly **one** page-table
`QueryInfo` for its captured LR. The new
`EDEN_GUEST_FAULT_LR_MAP` event records queried address,
mapping range and state. It never reads guest memory, does not
interpret a mapped LR as proof of JIT correctness, and does not
mask the original `pc=0x4` fault. On hardware, compare this
record to `EDEN_GUEST_CODE_RANGE` and the saved fault
registers; separate findings from the unrelated GPU-progress stall.

A core-ready host CI run must cover these source invariants and
the actual native case TGA decoder before the next full All-On
native build can be described as a qualified release candidate.


## Native All-On candidate with cancellation and LR fault map

The native test candidate following the successful
`43a82765` reference build includes:

- The per-face GL cache invalidation fix and worker serialization;
- Immediate retry eligibility after cancellation, instead of leaving an
  incomplete fetch rate-limited for five minutes;
- One-shot `EDEN_CASE_DRAW` state reporting after GL texture readiness;
- One fatal-only `EDEN_GUEST_FAULT_LR_MAP` page-table metadata query
  (no guest memory dereference);
- Host regressions including C++ BGRA decode, orientation, and truncated
  scan rejection, plus cancellation/guest fault source invariants.

The build is development-only, not published. A green CI build qualifies
the archive and native linked code, not console FPS, GPU/HUD synchronization,
or runtime guest crash repair. For the next console session, record the
exact git SHA and preserve logs without resetting the cache unless prompted
by new evidence.
