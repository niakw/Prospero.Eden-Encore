# Eden Encore — native capture review (13 October 2026)

Status: **hardware-observed regressions; next candidate not yet console-qualified**.
Source: user-provided native `stderr`, `heap` and network metadata logs
from the R457 All-On candidate. This is not evidence of a native fix.

## Separate the three user-visible issues

1. **Game input:** the launch receipt records
   `mode=dual_manual menu_a=0 menu_b=1 match_a=1 match_b=0`.
   The runtime emitted `EDEN_PAD_GAMEPLAY_PROFILE mode=match`,
   then `mode=menu`, then `mode=match`. The physical chord was
   detected; this disproves the theory that the profile was never activated.
   The launcher does **not** read the title's internally saved action preset.
   A controller remap changes guest HID button events, not guest artwork.
   One bounded `EDEN_PAD_GUEST_FACE` receipt per manual switch has been
   added to report actual A/B/X/Y to physical face-button wiring. The
   match behavior observed by the player remains unqualified.
2. **In-game prompts:** launch reports `In-game button art: ... original`
   with `rule=nintendo_selected`, and `Mods: none`. No verified
   alternate RomFS art was loaded. Rendering an alternate pad image or
   action symbols requires independently verified art; HID remapping
   cannot do it. Never silently inject an unverified pack.
3. **Gameplay HUD/rendering:** screenshot confirms guest-origin pad art,
   but it does not prove the cause of any missing or flickering in-match HUD.
   In the observed interval, `EDEN_GPU_DRAW_DROP` tracked
   `no_pipeline`, `configure_rejected`, `built_pipeline_failed`,
   `descriptor_buffer_full` and `worker_pipeline_failed` at zero.
   Other render-path faults remain possible. Avoid declaring this fixed.

## Frame-time evidence

Current `heap(20261013-180236).log` contains 136 complete
5-second frame reports. The median reported FPS is approximately 30;
the slowest window is about 7.1 FPS. Worst single present gap:
**2023.786 ms** (total frame 2890). Other gaps:
1656.256 ms (frame 2752) and 1528.253 ms (frame 2854).
The 2890 window also reports GPU fence time 1562.976 ms,
JIT compilation 3683.511 ms, and guest IPC 2040.396 ms
(as per-window accumulated phase times, not additive wall time).
This is a real frame-progress problem, not just a 30 FPS target.

The older `heap.prev.first.log` reports 609 complete frame windows,
median approximately 30 FPS and worst gap 532.229 ms. These captures
are not matched scene/time experiments and must not be used to claim a
controlled regression or improvement.

## CPU topology and next source candidate

Native logs show 13 allowed logical CPUs, unverified physical SMT,
and `EDEN_EXPERIMENT_CPU ... physical_verified=0`. The earlier
hypothetical paired layout pinned five primary tasks and restricted the
secondary scheduler pool to `0x1003` (three logical CPUs), including
graphics, audio and service workers. This was a speculative allocation
and may contribute to starvation.

The next source candidate **fails closed on unknown physical topology**:
it does not activate speculative guest/GPU pinning and it leaves
scheduling to the kernel. The verified physical-topology path is
unchanged. This is a candidate mitigation, not proof of better FPS.

## Scope and proof gates

- Run source/host regression checks first, including the actual mock
  affinity contract and controller mapping assertions.
- Require a green native build, compiled application integrity and
  downloadable test artifact before asking for another hardware test.
- Compare equal scene durations and track FPS, worst frame gaps,
  guest IPC/JIT, GPU fences, renderer artifacts and actual controller
  actions. Do not judge gameplay using the FPS median alone.
- Keep saves, title controls and old logs intact. Do not require
  blanket cache deletion to make this candidate run.
- Treat guest networking retries as a separate possible contributor:
  network logs show many denied DNS requests, but they do not establish
  that those calls cause the worst frame gaps.
