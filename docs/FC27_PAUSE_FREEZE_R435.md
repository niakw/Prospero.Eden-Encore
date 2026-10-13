# FC27 pause-menu freeze — R435 triage (2026-10-13)

## Session evidence, not speculation

Four user-provided logs: `heap.first.log`, `heap(20261013-133052).log`, `stderr(20261013-133054).log`, `network-accepted(4).log`. These are **diagnostic inputs**, not stored inside the repository.

- Physical DualSense Options registered **2 rising edges**, both published as virtual Nintendo Plus (`EDEN_PAD_INPUT_CHAIN options_edges=2 published_plus_edges=2`, first visible around poll 252,500). This is **not** proof the guest's Npad shared memory observed the bit.
- The Sony pad reader keeps returning records without syscall errors. The number of **usable** records stops at **1,114,171** around poll 403,750, while raw sample counts continue to 2,695,497. `is_usable` requires `sample.connected != 0` and a non-intercepted flag. `intercepted=0`, so those later samples have `connected=0`. The summary's `connected=1` only means the application's primary pad handle remains open. This **later** disconnect (possibly sleep) does not establish why the original pause became stuck; do not blindly reopen or remap a controller during a match.
- Across 1,022 five-second performance windows, the Vulkan presenter continues to show **~30 FPS** after frame 20,000. Among frames 20,000–90,000, no `EDEN_VULKAN_FRAME` window reports an image >=50 ms; across the initial 20,000 frames, long first-use stalls remain. The render loop continues, so this is **not** a proven whole-GPU deadlock. Re-rendering one paused screen at 30 FPS does **not** imply FC27's UI event loop is responsive.
- IPC, draw, buffer-cache and texture-cache counters continue advancing while the output image remains apparently frozen. In the last displayed window JIT compilation is 0 and the Vulkan present fence latency is small. Thus changing Vulkan resolution or clearing shader cache is not evidence-based treatment of the pause freeze.
- The offline audit records repeated denied EA endpoints, but denial alone does not show that opening Pause is blocked on a specific network call. No confirmed GPU fault or OOM appeared in supplied excerpts.

## Missing boundary to instrument

The pinned Eden HLE implementation writes `pad_state` to the emulated `fullkey_lifo`. R435 generates a **private, dev-only** `npad_pause_diag.cpp` derivative at CMake configure time, leaving the source SHA of Eden untouched. It emits:

- `EDEN_NPAD_PLUS_LIFO`: bounded rising-edge count when the emulated fullkey Npad shared-memory writer records Plus.
- `EDEN_NPAD_PROGRESS`: a rate-limited heartbeat every 1,500 fullkey writes, proving guest HID keeps publishing new samples during the pause.

This does not change mapping, use synthetic presses, acquire GPU locks, reset the HID service, alter frame pacing or claim guest game code consumed a LIFO entry. If the Plus event is present and the game's pause still locks, investigation moves to the game's UI/HLE wait; if it is absent while `published_plus_edges` increases, inspect Npad activation/style and HID guest service filtering. The input lock story remains open pending this precise handoff.

## Qualification

R434 native PS5 All-On build has succeeded: https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38385105638. R435 source-only preflight and a new PS5 dev native build must pass before any console validation. No source tree other than `dev/ps5-sparse-jit` is used.
