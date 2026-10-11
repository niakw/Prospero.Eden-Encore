# R318 — Skip feedback-loop texture scan for PS5 color-only passes

Branch: `dev/ps5-sparse-jit`. Pinned Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Code reasoning

The pinned `CheckFeedbackLoop` can request a GPU barrier only if the active **depth** attachment is sampled through another view. When `rt_active_mask` has no depth bit, the search over sampled views cannot return true, but the original code still evaluates the bindings and R315 also compares/stores the full view-ID snapshot. This takes place inside `GraphicsPipeline::ConfigureImpl` while the rasterizer holds **both** GPU cache locks.

## PS5-only improvement

`headless/backports/eden-ps5-feedback-loop-no-depth-fastpath.patch` exits immediately after recording a false decision and clearing R315's snapshot when no depth is active. The original code and barriers remain for depth-active passes. Clearing the snapshot guarantees a depth-active pass with bound textures re-evaluates the decision even if an unexpected frame retains the same serial counters. Upstream/non-PS5 code is unchanged. No locks removed and no replacement GPU barrier inserted.

The real production patch is replayed after R314, R315, R317; the existing pinned-source host C++ regression now includes color-only, subsequent depth-reactivation and unchanged upstream behavior. This optimizes only eligible no-depth draws, **not** the expensive 3D depth-enabled passes behind the major FC27 saccades. No on-console FPS gains claimed.

R315–R317 host gates are green; no native build newer than R314 as of this document.
