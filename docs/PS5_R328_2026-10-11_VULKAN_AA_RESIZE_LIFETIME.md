# R328 — Explicit FXAA/SMAA resource lifetime on native Vulkan framebuffer changes

Canonical active branch: `dev/ps5-sparse-jit`, pinned Eden mirror `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Verified source defect

`src/video_core/renderer_vulkan/present/layer.cpp::Layer::RefreshResources` previously reset the `anti_alias` variant via `anti_alias.emplace<std::monostate>()` **before** `ReleaseRawImages()` waited on previous image ticks. An FXAA/SMAA instance owns per-image framebuffers, descriptors, images and Vulkan pipelines. A resize or guest framebuffer pixel-format change while antialiasing was active could thus destroy still referenced Vulkan resources. `SetAntiAliasPass` also `emplace`s a new variant immediately on a live FXAA↔SMAA or active→none filter change. Neither method had a GPU completion wait before destroying the old filter.

This is distinct from R327's `BlitScreen::DrawToFrame` layer-count change. It can arise while the number of guest framebuffer layers remains the same.

## Minimal guarded correction

The PS5-only derived source `vulkan_present_layer.cpp`, built **instead of**, not alongside, the pinned `renderer_vulkan/present/layer.cpp`, adds two guards:

- On changed guest framebuffer width, height or pixel format, **only if an old FXAA/SMAA pass exists**, `scheduler.Finish()` then `device.GetLogical().WaitIdle()` before `anti_alias.emplace<std::monostate>()` and the original `ReleaseRawImages()`.
- On an actual anti-aliasing mode change with a currently live FXAA/SMAA pass, the same drain precedes replacement with the new pass or `std::monostate`.

Nothing new runs on unchanged image dimensions and AA settings, or on first-time allocation. No change to FSR EASU/RCAS, texture scaling, cache correctness, Nvnflinger, the guest framebuffer data, command batching, display resolution, or original non-PS5 upstream source. Avoid unvalidated extra waits on every frame.

## Reproductions and gates

`tools/check-ps5-vulkan-aa-lifetime.py` fetches and SHA-verifies pinned Eden `layer.cpp` (Git blob `14935f92bb450973e85237fed52f8dea6d172688`), applies the exact **production generator edits**, compiles and executes both complete C++ Layer methods with fake GPU-live FXAA/SMAA resource owners. The pinned unmodified method fails the resize scenario; the corrected method passes resize, stable dimensions, FXAA→SMAA, SMAA→none, none→FXAA, and checks wait counters. `vulkan_present_layer.cpp` also passed `x86_64-sie-ps5` C++ `-fsyntax-only` against an actual native compile database. Both source and native CI workflows now include the host fixture. Full native compilation/staging and PS5 gameplay evidence remain necessary before calling the fix user-visible; it is not yet proof of eliminated FC27 grass pixelation or missing HUD.

Previous verified R327 source regressions: [#38171048346](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38171048346) (9/9 PASS); R327 native compilation [#38171093722](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38171093722) was running when this patch was assembled. Keep previous native-green R326 binary until R327/R328 are fully validated.
