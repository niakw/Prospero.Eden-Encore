# R327 — Explicit Vulkan layer lifetime drain on guest framebuffer count changes

Canonical branch `dev/ps5-sparse-jit`, pinned Eden mirror `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`. No short-lived branch or release.

## Root source hazard

The pinned `src/video_core/renderer_vulkan/vk_blit_screen.cpp::BlitScreen::DrawToFrame` rebuilds its `layers` whenever `framebuffers.size()` changes. It called `layers.clear()` without a full GPU wait. A `Layer` owns raw images/views, a per-layer descriptor pool, antialias images, and (under FSR) EASU/RCAS images and their descriptor sets; scheduled Vulkan commands can still refer to these after `DrawToFrame` returns. The `Layer::~Layer` wait only covers its raw `resource_ticks`, not necessarily all filter and downstream Vulkan work. Independently, changing the scaling filter or render size already invokes `BlitScreen::WaitIdle` before destroying the layer collection.

## Minimal PS5 native-only adaptation

For an **actual change in layer count** with existing layers, invoke the established `WaitIdle(device)` *before* `layers.clear()`. `WaitIdle` performs `present_manager.WaitPresent()`, `scheduler.Finish()` and `device.GetLogical().WaitIdle()` to protect outstanding Vulkan resource owners. It does not run on a stable frame count, or on initial construction from an empty collection. `#ifdef PS5_NATIVE` preserves upstream non-PS5 behavior. No changed images, alpha, filters, barriers, game glyphs, scaling factor, frame-skip or queue capacity. A layer-count transition may incur a drain, but this is safer than destroying live GPU resources.

## Qualification

`tools/check-ps5-vulkan-layer-lifetime.py` compiles and executes the generator's **exact** C++ replacement in a GPU-busy fake-layer harness, testing initial creation without drain, stable count without drain, 1→2 transition (drain before destructor), 2→0 transition, and 0→3. The unchanged upstream fragment fails the same runtime ordering assertion (negative control). The real generated `vulkan_blit_screen.cpp` also passed `-fsyntax-only` using an existing PS5 `x86_64-sie-ps5` native compilation database. Native CI builds and archive check remain independent gates.

This closes a concrete potential use-after-free on composition changes, **not** proof that it cures FC27's occasionally missing score/time HUD or remaining terrain LOD and pacing problems. Console validation is not requested from this source-only fix. The R326 All-On native build #38170426022 was already green before this edit; keep it available until R327 completes its own gates.
