# Eden Encore — PS5 R1 gameplay/launcher regression, 2026-10-10

Scope: PS5 firmware 13.60, native R1 binary built 2026-10-10 18:28:45, source branch `dev/ps5-sparse-jit`.
Evidence: user-reported FC27 tests 1–3, BOTW Ultra test, `crash-20261010-204114.txt`, `crash-20261010-204114-stderr.log`, `stderr(10).log`, `heap(9).log`, and native boot traces. The evidence is not a post-fix console test.

## Reproduced/confirmed findings

- Launcher Triangle game settings: holding Down until the lower entries causes a crash. Crash report at 20:41:14: main-thread SIGSEGV, 47 seconds after startup, address `0x46e03b00`, launcher state; largest free block 11,770 MiB. **Not a bad_alloc.**
- Source audit found a precise OOB path in `headless/prosperoeden/pe/ui/library.cpp`: `kGameAbout` contained 7 entries but `option_` could index up to `row_controls` (9). Fixed by 10 matched captions, static size check, index guard, and stale library-selection guards. Hardware confirmation is pending.
- FC27 title `0100C49025D3E000`: DualSense and static A/B/X/Y input are recognized, but runtime logs explicitly state `In-game button art: Nintendo original (rule=nintendo_selected)`, `Mods: none`. The embedded glyph catalogue contains no rules (`headless/glyph_overrides_generated.h`, `data/glyph-overrides.json`). Correct input mapping **does not** imply PlayStation graphics in-game.
- Native DEV build output reported `EDEN_VULKAN_MEASUREMENT quiet=0 captures=1` even when the user disabled detailed logging. The default driver logging policy in the DEV build was independent of the UI preference. Corrected so `PS5VK_QUIET_LOG` becomes 1 whenever detailed logging is off or explicit performance-run is active; scanning/capture policy was **not** modified to avoid risking rendering changes.
- CPU affinity: 16 logical processors reported, 13 allowed at probe time, topology verification rejected; `CPUCore_3` was pinned but showed zero guest compilations across the sessions. This does not establish that the PS5 is blocking cores or that the guest has four runnable CPU threads.
- JIT sparse: virtual reservation was established, native committed pages increased during FC27. No indication in these logs that the specific launcher SIGSEGV was caused by memory exhaustion.

## Five-second frame-window summary

| Session | Title | Windows | Avg FPS (of window FPS) | Windows under 25 FPS | Late frames over 50 ms | Worst frame |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | FC27 | 64 | 28.13 | 10 | 322 | 1466.7 ms |
| 2 | FC27 (cache cleared; logs disabled) | 170 | 28.77 | 17 | 491 | 5141.2 ms |
| 3 | FC27 (cache retained; logs re-enabled) | 196 | 28.71 | 19 | 746 | 619.4 ms |
| 4 | Zelda BOTW Ultra | 16 | 27.45 | 3 | 158 | 396.1 ms |

These runs differ in duration and scene, so raw late-frame counts are **not** valid A/B improvement scores. FC27 reaches 30 FPS in many windows but still suffers long presentation gaps. BOTW Ultra exhibits similar pacing problems. Emulated frame-rate/host presentation is not equivalent to a complete GPU-occupancy or input-latency measurement.

## Changes on dev branch

- `dd11aade`: fix Triangle game settings hint OOB access.
- `7cdcfb2b`: defend against stale library selection.
- `f371f4c1`: driver traces quiet by default when detailed logs are off.
- `e646d709` / `8b896619`: add and correct source regression checks.
- `292c3d06`: include UI source checker in core-only preflight.
- `0f95cb8f`: use existing localized captions for all ten setting rows, avoiding a French translation-catalog failure.

## Not yet fixed/qualified

1. Confirm Triangle dialog traverses every item without SIGSEGV on the next PS5 package.
2. Confirm quiet driver path reduces log rate and frame-time spikes in a **matched** FC27 scene, with cache preserved; do not assume large gains.
3. Investigate long-tail pacing (guest JIT/cache, GPU submits, binder/dequeue waits, video synchronization, shaders) with comparable capture windows. Do not infer GPU underuse from CPU idle counters alone.
4. Qualify Zelda Ultra separately; do not silently downgrade the graphics preset or claim constant 30 FPS.
5. In-game PS glyph packs remain unsupported for FC27 until an actual verified title/update-specific graphic pack, manifest rule and loader activation exist. Do not pretend input remapping modifies guest textures.

**Build/PS5 validation:** no new PS5 binary was compiled as part of this note. Host source checks and hardware testing are separate steps.
