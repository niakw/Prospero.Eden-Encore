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

## Candidate native correctness fixes after the failed c3774d3e test

The source-only analysis found that the **active** shipping backport already has a broadcast dequeue epoch (`vendor/encore-active/eden-backports/src/core/hle/service/nvnflinger/buffer_queue_core.{cpp,h}`). An attempted duplicate edit of pristine `vendor/sources/eden` was restored; keep that pinned source immutable. The effective new native correction is generated in `headless/CMakeLists.txt` as `buffer_queue_consumer.cpp`: when `AcquireBuffer` drops an old queued buffer and then returns `PresentLater`, notify producer waiters before the early return. This preserves queue ownership, timestamp semantics, and all GPU command ordering. A second change removes the periodic blocking `fflush(stdout)` from the Vulkan rendering callback; the independent native log-pipe consumer remains intact. The first-frame startup flush is unaffected.

`tools/check-ps5-buffer-dequeue-generation.py` replays the *active* backport source on the host with 400 concurrent waits, checks the derived native consumer override contracts, and guards the nonblocking periodic render path. Hardware runtime outcomes remain unknown: neither fix is labeled a demonstrated FC27 freeze solution, and no game-specific remapping correction is included. Both title actions and saves were left untouched. Build and qualify as one All-On candidate only.
