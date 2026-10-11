# R332 — FC27 menu freeze: trace physical DualSense input without changing behavior

Single branch `dev/ps5-sparse-jit`. New PS5 FTP logs at `/data/prosperoeden/logs/` from October 11, 2026, show FC27 at Vulkan output 1440p, game resolution 1×, FXAA, 60 Hz. The user observed a completely frozen menu image during controller reassignment, including problems assigning Square and Triangle.

## Current evidence

A series of five-second windows around the frozen menu still reports 30.0 FPS, 0 frames later than 50ms, 0 GPU producer queue waits, around 36,750 draws, and around 6,000 IPC calls per 5s. The guest and GPU threads therefore continue doing work; **a completely idle GPU or the earlier in-match full-queue stall is not demonstrated**. FPS/draw counters alone do not prove successive pictures differ. Do not claim the hang fixed.

The game's session logged `EDEN_PAD_MAPPING_FIXED ... layout=0 a=0 b=1 x=2 y=3`: Cross→guest A, Circle→B, Square→X, Triangle→Y. This is the configured mapping, not proof the buttons arrive at the guest while stuck. Importantly the native `pad.cpp` compile command has **no `EDEN_DEV_PROFILE`**. Its original `EDEN_PAD_EVENT` lines are consequently compiled out, explaining why they are absent from stderr even when main.cpp logs `EDEN_PAD_INPUT mode=dualsense`.

## Patch

The PS5 `Pad::Poll` writes a single `EDEN_PAD_HEARTBEAT` line every 1,250 polls (~5s), and only when native Detailed Logging is ON. Fields: cumulative polls, read/usable/intercepted samples, errors, last scePadRead return, connected players, raw button bits, physical rising-edge counters for Cross/Circle/Square/Triangle, and the immutable destination mapping of guest X/Y. `headless/pad_diagnostics.h` is a minimal dependency-free helper for edge counts. No per-poll disk writes, stream flush, guest HID changes, layout changes, queue/fence modification or resource allocations. No new work in the quiet native path beyond a conditional.

The C++ host fixture `tools/check-ps5-pad-freeze-observability.py` replays actual edge logic and checks quiet-only logging and correct source integration. Native `pad.cpp` compiled successfully under the existing `x86_64-sie-ps5` compiler database with current source/include paths. Both CI workflows include the fixture.

## Next interpretation

If the heartbeat disappears while Vulkan frame counters progress, the input poll worker needs investigation. If the heartbeat remains but samples stop, check native controller reads. If Square/Triangle edges increase while the menu remains unresponsive, investigate the guest HID or FC27 UI's reassignment rules, rather than swapping button meanings arbitrarily. One later menu-focused run of this instrumented binary will distinguish these cases. It is **not** yet a verified freeze fix.
