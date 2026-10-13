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
