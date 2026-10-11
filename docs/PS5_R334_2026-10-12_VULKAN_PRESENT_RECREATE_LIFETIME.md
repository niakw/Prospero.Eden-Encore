# R334 — PS5 Vulkan presentation frame dependency lifetime

Canonical branch `dev/ps5-sparse-jit`, no separate branches. Pinned original Eden source: `src/video_core/renderer_vulkan/vk_present_manager.cpp` at `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`, Git blob `3491f8fb7563f2557a476fec8edb4f220f5d27fc`.

## Reproduced Vulkan resource destruction bug

`PresentManager::RecreateFrame()` overwrites `frame->image` with a new `VkImage` *before* freeing the old frame's `VkFramebuffer` and `VkImageView`s. The frame's old views and framebuffer are still live when their backing image is destroyed by the RAII image move-assignment. This violates Vulkan object lifetime constraints independently of R331 (which fixed **a different** `Layer::ReleaseRawImages()` path). A new `frame->image_view` is also created before the old framebuffer referencing the prior image view has been freed. `vk_blit_screen.cpp::BlitScreen::PrepareFrame` and its resource-change path call `WaitIdle(device)` before recreating, so additional per-frame GPU waits are unnecessary: the remaining problem is **host-side Vulkan object teardown order**.

## Minimal PS5 correction

The PS5 source generator now clears the old `frame->framebuffer`, then `frame->storage_view`, then `frame->image_view`, **before** replacing `frame->image`. Remove the redundant later `storage_view` reset in the same generated function. No changes to queue budgets, present scheduling, guest input, GPU synchronization, the FSR/FXAA algorithm or memory allocations on ordinary unchanged frame extents. Changes are only in the frame reconstruction path; parent Vulkan image always outlives child views/framebuffer.

## Qualification

`tools/check-ps5-vulkan-present-frame-lifetime.py` pins and Git-blob SHA-verifies the real upstream source, replays all exact source-generator patches, checks the complete relative order in the **real** `RecreateFrame` method, then compiles and runs the extracted lifecycle operations with host RAII stand-ins. Original pinned order **FAILS** when replacing an image referenced by views/framebuffer; adapted R334 order **PASSES** and cleans up cleanly.

- Local macOS host fixture PASS, both with local pinned source and network GitHub source.
- Generated real `vulkan_present_manager.cpp` `clang++-18 --target=x86_64-sie-ps5 -fsyntax-only` **PASS**, except pre-existing SDK warning about `-Wno-error-all`.
- `tools/check-vulkan-present-source-replay-host.py` **PASS**, `tools/check-ps5-present-equal-copy.py` **PASS** with valid macOS15 SDK selected, Python source syntax PASS.
- CI source and complete native PS5 build must be green independently; these tests are not on-console proof.

The user-reported FC27 menu input freeze and severe match stutters remain open, with distinct observed queue-state signatures; this corrects Vulkan object lifetime on frame-size changes, not an asserted fix for those symptoms.
