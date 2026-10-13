# Eden Encore — FC27 R400c full-match graphics, pacing and liveness audit

**Evidence:** FC27 native PS5 FW 13.60 test, build R400c `f00ed08581957e651d54def355d8716c90a757af` (2026-10-12). Five 2048×1152 gameplay captures and eight text log files provided by the tester on 2026-10-13. **The logs and screenshots are retained by the tester; do not publish them or local network addresses as CI artifacts.**

**Test environment:** guest title `0100C49025D3E000`; Vulkan, docked, 1× guest resolution, 1440p output, bilinear scaling, FXAA, 60 Hz requested / 59.94 Hz selected. Tester manually cleared the shader/JIT caches before play; loader reported zero stored pipelines and a lazy persistent Vulkan shader cache. The boot/source identifier establishes this as R400c, **not** R402.

## Reproduced visual problem

- At the beginning of the supplied capture sequence: scoreboard, clock, both player identification strips and minimap visible.
- Later captures: scoreboard disappears while gameplay and the minimap persist; in the final capture the lower strips retain their backgrounds but their logos/text/indicators are missing.
- The grass is soft/pixelated in motion according to tester; still screenshots are insufficient to prove a texture-alias fault or pixel reconstruction issue. Bilinear 1080p guest → 1440p output can add softness but **cannot alone explain entire HUD elements vanishing**.
- Nine `EDEN_GPU_DRAW_DROP reason=no_pipeline` drops accumulated by approximately frame 6267 and **did not increase afterward**. The native Vulkan path currently allows async shader creation to return `nullptr` for nontrivial unbuilt pipelines (`PipelineCache::BuiltPipeline`); this is a plausible transient draw-loss mechanism, **not proof that these specific nine drops correspond to the missing HUD**, especially after that frame.
- `configure_rejected`, `built_pipeline_failed`, `descriptor_buffer_full` and `worker_pipeline_failed` draw-drop counters remain zero.
- Four bounded `EDEN_GPU_PRMT_IMM_INDEX` diagnostics appear. Their existence alone does not establish a causative hardware shader bug.

## Quantified temporal behavior

`heap(20261012-235826).log` has **192** `EDEN_VULKAN_FRAME` windows (~5 seconds each) and ends at 28,056 frame callbacks. Parsed values:

| Metric | Result |
|---|---:|
| Median reported FPS per window | 30.000 |
| Windows with reported FPS ≥29.9 | 151 / 192 |
| Windows with FPS under 25 | 14 / 192 |
| Windows whose worst interval exceeds 100 ms | 28 / 192 |
| Windows whose worst interval exceeds 200 ms | 16 / 192 |
| Windows whose worst interval exceeds 500 ms | 6 / 192 |
| Maximum individual frame interval | 3,000.831 ms (window ending frame 3229) |
| Other large intervals | 2,144.509 ms at 1376; 1,430.331 ms at 3905; 937.096 ms at 3977 |
| Maximum 5-second window of guest cache contention | 22,145 contended locks at frame 16748 |
| Its aggregate wait | 359.838 ms across contending threads |
| Buffer-domain cumulative locks blocked at final sample | 266,226 (3,500.282 ms aggregate wait) |
| Texture-domain cumulative locks blocked at final sample | 35,161 (5,793.783 ms aggregate wait) |

These aggregates are **not a single-thread wall-clock stall time**: multiple guest/GPU threads can wait concurrently. At a typical 30-FPS sample, `gpu_idle_ms` measures the emulator's GPU worker idle for ~3–4 of 5 seconds; it is **not** a PS5 hardware GPU utilization reading. Likewise the scheduler's 30-FPS plateau does not prove 33.3-ms frame delivery under every camera motion.

`EDEN_FRAME_PRESSURE` identifies concurrent windows with large JIT compile work and guest IPC service time, especially on a cold startup. Lock contention remains strong later. This is **not** evidence that more JIT address space or higher resolution will improve pacing. Heap failures were 0 in sampled diagnostics; the trace does not establish GPU/device OOM.

## The final user-observed game freeze

Last recorded performance snapshot: `mono_ns=203094496491967`. The user exited through the shortcut at `mono_ns=203111719628873`, about **17.223 seconds later**; the graphics logger produced no further 5-second performance snapshot in that interval. It is consistent with the reported unresponsive end-of-match period but **cannot distinguish a deadlocked GPU renderer from stopped guest scheduling, a paused game, or profiling output interruption**. The run then recorded `core_shutdown` and `core_destroyed` and a successful return to the launcher. There is **no explicit crash signal or native OOM in these supplied logs**. Existing `game_liveness.h` requires 30 seconds without GPU progress before emitting its first diagnostic, so a shorter terminal stall has no stall-specific provenance.

The independent pad polling thread survived: physical Cross/Circle/Square/Triangle edge counters increased and no physical controller read errors were reported. Do not mistake input polling for confirmation that the guest HID service consumed presses.

## Controller mapping fact (amends the earlier R402 hypothesis)

R400c's log: `EDEN_PAD_MAPPING_FIXED title=0100c49025d3e000 layout=0 a=0 b=1 x=2 y=3 title_override=1`, followed by `Controller profile PlayStation, map {}`. **The native launcher already resolved the correct FC27 title ID.** Thus a missing title-ID filename fallback was **not** the cause of this particular session's mapping symptom. The `title_override=1` diagnostic can mean a game-specific *layout selection* without `own_mapping`, rather than a saved custom table. R402 adds explicit `own_mapping` logging and a genuine title-ID fallback for other cases; it does **not** prove or repair this session's missing custom mapping. Audit `headless/prosperoeden/pe/ui/library.cpp` where cycling game-specific layout sets `own_mapping=false` and removes its map from the saved JSON. Do not silently present R402 as proven in-game fix.

## Network log interpretation

The supplied `network-accepted(3).log` has 7,631 entries, including 7,400 denied guest DNS events and some permitted **native** local discovery activity. Its Unix timestamps span about **nine hours**, so totals must **not** be attributed to this one 16-minute match. The displayed guest EA queries were denied. There is no evidence from these records of an accepted guest connection to EA.

## Actionable source audit order

1. Inspect and qualify the guest color/alpha render-target and texture cache alias/invalidation path **and** descriptor generation lifetimes. Cross-reference `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`, `vk_graphics_pipeline_cost.cpp`, `vk_texture_cache_cost.cpp` and pinned Eden upstream. The nine no-pipeline draw drops are bounded, not a license to disable async shader rendering globally.
2. Profile and address the guest buffer/texture cache lock ownership, wakeups and GPU submission pacing, preserving correctness before reducing locks. Avoid conflating total mutex waits across threads with single-frame hitches.
3. Trace CPU/JIT/IPC stalls separately from GPU worker idle. PS5 SMT grouping remains unverified and the fourth emulated CPU's compilation counter is zero in this run; neither observation justifies pinning to fictitious physical cores or increasing the frame cap blindly.
4. Improve bounded short-freeze provenance in `headless/game_liveness.h` and correlate guest CPU phases, GPU completed commands and last frame callbacks. Never kill a guest based on observational stall suspicion.
5. Verify the per-title mapping survives selecting game controller profiles: `headless/prosperoeden/pe/ui/library.cpp` currently intentionally sets `own_mapping=false` on profile change, even if a custom map was previously saved.
6. When fixing confirmed root causes, run host source/sanitizer tests, then one consolidated PS5 native build. Do not request repetitive whole-match tests before there is a materially different binary.

**Scope:** evidence analysis and preflight only. No gameplay-rendering, cache ownership, scheduler or memory behavior is changed by this report.
