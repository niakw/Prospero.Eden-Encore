# R336 — Thread-safe PS5 Vulkan swapchain metadata snapshots

Branch `dev/ps5-sparse-jit`. Verified against Eden mirror base 9 September 2026, SHA `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Concurrency issue

PS5 forces `Settings::values.async_presentation=true` for Vulkan. In this configuration the `VulkanPresent` thread can call `RecreateSwapchain()` (which updates the swapchain image count and formats), while the GPU's composition worker calls `swapchain.GetImageCount()`, `GetImageViewFormat()`, or (for LSFG) `GetImageFormat()`. The original `Swapchain` fields are **not atomic**. This is a C++ data race with potential inconsistent image count/format and hence incorrect intermediate render resources. `PresentManager::image_count` is also updated by the presentation worker but read by the renderer via `MaxExtraFrames()`.

Eden upstream fixed much of this in its 2026-10-08 commit `3cdd2ce141224079ce1dc8bfb4be7edc113aca02` (#4509), by making present frame count atomic and publishing swapchain image count and image format to atomic snapshots read from `RendererVulkan::Composite`. The PS5 source generator R336 backports those targeted semantics, **and** includes the view format needed by our PS5 composition and loading HUD.

## Changes

- `PresentManager` now uses atomic frame count and presenter-owned `swapchain_image_count`, `swapchain_image_format`, `swapchain_image_view_format` with nonmutating atomic getters. On initial creation and any swapchain recreation, `SetImageCount` publishes updated metadata after querying the actual underlying swapchain.
- `RendererVulkan::Composite` uses the snapshots rather than reading unprotected `Swapchain::GetImageCount()`, `GetImageViewFormat()`, or `GetImageFormat()`.
- Our PS5-specific `headless/vulkan_loading.inc` also used direct count/view-format getters and was changed to use the snapshots. Ordinary GPU composition, native PS5 loading animation, FXAA/FSR, present frame fences and resources retain existing execution ordering.
- No locks added to per-frame calls; no per-frame logging or GPU waits. These atomics **prevent unsynchronized direct reads**, but they are not a transactional three-field snapshot. Swapchain recreation is infrequent and independent atomics do not guarantee all three values originate from the same recreate epoch. Do not claim complete elimination of all frame pacing or texture artifacts.

## Evidence

`tools/check-ps5-vulkan-swapchain-snapshot.py` verifies exact replay of source generator edits against all three real pinned files, checks the new atomic types and the two consumer paths (normal render + loading), rejects lingering direct getter reads in those paths, and host compiles/runs a two-thread snapshot update/read test. Generated `vulkan_present_manager.cpp` and `vulkan_renderer.cpp` have passed PS5 `clang++-18 --target=x86_64-sie-ps5 -fsyntax-only` (with existing warning for `-Wno-error-all`). Existing render-present host tests and new R334/R335 tests remain independent and both GitHub CI workflows include the R336 gate.

The current FC27 menu freeze and in-match stutters are not yet qualified against this change on the PS5, and no user console retest is requested. This is a source-level race correction, not proof of a particular user's observed visual symptom.
