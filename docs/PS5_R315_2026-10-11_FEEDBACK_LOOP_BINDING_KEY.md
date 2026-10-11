# R315 — PS5 texture-bound feedback-loop barrier cache correctness

Branch: `dev/ps5-sparse-jit`. Pinned Eden: `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`. Target: FC27, `0100C49025D3E000`.

## New hardware observation (11 October 2026)

User reports R314 visuals **slightly improved** and stutter **slightly reduced**, but both still present. No quantitative R314 timing delta. User is independently checking quiet mode; no more captures required at this stage.

## Verified source-level defect

Pinned `TextureCache<P>::CheckFeedbackLoop` caches the previous decision by `render_targets_serial` and `texture_bindings_serial`. The latter changes when texture/sampler table *bases* synchronize, but is **not** incremented merely because another shader selects a different existing view ID from those tables. R314 increments it on a NULL-view recovery but does not cover switching between already-valid views. With `barrier_feedback_loops` enabled (Eden's default), two consecutive draws using different view sets can reuse the first draw's decision: redundant barrier on the second draw (cost) or missing depth feedback barrier (correctness).

## Narrow change

`headless/backports/eden-ps5-feedback-loop-view-key.patch` adds a per-cache snapshot of actual bound view IDs **only on PS5**; the existing two-serial key still qualifies the fast path when the bound view order and IDs also match. When they differ, evaluate the original feedback logic and replace the snapshot (vector capacity reused). Original GPU barriers, render target logic, locks, and R314 recovery remain unchanged. No unconditional GPU barriers, no change to 512-draw cap, no user-visible setting change, no shipping/upstream behavior change.

This is a *source-proven decision-cache defect*, **not proof** of an FC27 performance or rendering cure. Equality checking costs O(number of sampled views) per call; this must be weighed against correct barrier decisions on actual hardware, and could slightly raise CPU time on texture-heavy scenes.

## Validation and follow-up

`tools/check-ps5-feedback-loop-view-cache.py` verifies exact pinned Eden blobs, applies the production R314 then R315 patches, compiles/exercises the real function in PS5 and upstream variants; checks depth-alias → unrelated → depth-alias, unchanged/repeated, empty and inactive RT cases. Both core and native preflight include the fixture. No native test/build requested by this source change.

Other open issues: cache-lock contention with FillImageViews peaks (old sampled max 11.36 ms), JIT/GPU frame pacing, double 1440p→4K resampling, and intermittent guest content/texture quality. Do not alter guest write locks, barriers or VideoOut solely to raise displayed FPS.
