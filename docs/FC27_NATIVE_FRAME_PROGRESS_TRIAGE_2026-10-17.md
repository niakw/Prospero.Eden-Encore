# FC27 native frame-progress triage — 2026-10-17

**Evidence:** user-provided `heap(20261015-161206).log` dated
2026-10-15. **Session renderer: Vulkan** (log includes
`EDEN_STAGE backend=Vulkan` and the matching native Vulkan
frame/pressure diagnostics). The console additionally initializes
OpenGL/Gallium for display; that does not redefine the title renderer.

## Exact offline pairing

232 `EDEN_VULKAN_FRAME` intervals have 232 matching
`EDEN_FRAME_PRESSURE` intervals by total frame number.
All are aggregate reporting windows, typically ~5s.

- 192 windows hold ~30 FPS with `worst_ms < 50` (median JIT
  compilation 0.213ms, median aggregate cache wait 17.255ms).
- 13 windows contain a frame of at least 300ms (median JIT compilation
  1286.181ms, median aggregate cache wait 16.791ms).
- Of those 13, four have aggregate cache wait less than 10ms;
  nine have JIT compilation at least 500ms.
- Median JIT compilation in the four high-stall/low-cache windows is
  several seconds. This points away from a **texture-lock-only**
  explanation for the biggest isolated frames.

The 5-second window ending at frame 3432 shows 23.322 FPS,
worst frame 312.942ms, 529.773ms multi-thread cache wait, and a
texture-cache lock maximum of 285.317592ms (two texture waits >10ms).
The next window, ending at frame 3547, shows a 980.574ms frame but
only 16.791ms cumulative cache wait. Other >900ms frames occur with
very low contention (e.g. frame 2420: worst 948.203ms, cache wait
0.439ms, JIT compilation 5620.873ms).

In a clean late window, ending at frame 33997, 150 frames in ~5s
are counted as exactly `v2=150` with a 60Hz display: effectively
one frame per two refresh intervals (~30 FPS). This demonstrates
regular two-vblank pacing but does not identify whether the guest
game, emulator scheduler, or presentation policy establishes that pace.

## How the measurements are defined

`jit_ms` tracks the development Dynarmic per-core **compilation**
timers (`eden_jit_compile`), not observed physical GPU load.
The numbers sum work across guest cores and cannot be subtracted
from frame duration. `cache_wait_ms` sums blocked CPU callback lock
waits across threads; it does not identify the owner holding the
mutex or the specific frame impacted.

The native Vulkan rasterizer does acquire the buffer/texture cache
pair in `PrepareDraw`, and the texture cache alone for multiple
operations. The sampled `pair_held` phase is 1/16 draws and does
not cover every other mutex owner or all off-draw critical sections.
At frame 3432, its observed max is 34.197us, insufficient to
identify who actually held the texture mutex for 285ms.

The measured GPU worker queue-idle fraction is **not** physical GPU
utilization. The frame count and `v2` presentation histogram do
not prove a hardware performance ceiling.

## Operational priority

1. **Root cause of JIT bursts:** inspect compiled-block counts, cache
   invalidations, per-core timing and repeat compilation in slow
   intervals. Prove which JIT work affects presentation progress.
2. **Texture-cache owner only for the rare 285ms tail:** identify
   the owner/critical section before changing lock scope/order;
   never remove fences or move guest writes outside protection.
3. **HUD/presentation freeze:** distinguish GPU command completion
   from final swap/presentation; frame stats above prove both normal
   and late intervals, not the cause of a persistent HUD stall.

No native renderer/guest semantics are changed by this report.
The native post-store bridge #187 remains disabled. No console
build/release/game test is authorized by these observations.

`tools/analyze-ps5-cache-contention.py` now emits a deterministic
long-frame/JIT/lock classification with exact frame pairing.
`tools/check-fc27-cache-contention-classifier.py` exercises it
with synthetic records in host preflight. The original console
logs are private evidence, **not added to Git**.
