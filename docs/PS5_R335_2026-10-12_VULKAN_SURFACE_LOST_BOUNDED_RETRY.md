# R335 — Bound Vulkan surface-loss presentation recovery, abandon failed frame

Branch: `dev/ps5-sparse-jit`. Pinned Eden original base `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`, `src/video_core/renderer_vulkan/vk_present_manager.cpp` Git blob `3491f8fb7563f2557a476fec8edb4f220f5d27fc`.

## Confirmed source-level liveness defect

`PresentManager::CopyToSwapchain` contains a `while (true)` loop that catches `VK_ERROR_SURFACE_LOST_KHR`, attempts `RecreateSwapchain(frame)`, and repeats **forever** if the surface cannot recover. When using the background Vulkan presentation worker, an unrecoverable surface can keep that worker inside this infinite loop, preventing recycling its `Frame` and potentially hanging presentation. This is a real independent liveness bug; it **does not prove** that the user's FC27 menu freeze (where GPU/guest work continued at 30 FPS) has this same cause.

The upstream Eden project landed a specific fix October 8, 2026, commit `3cdd2ce141224079ce1dc8bfb4be7edc113aca02`, PR #4509. Its relevant Vulkan portions introduce `MAX_PRESENT_ATTEMPTS=3`, a bounded retry loop and `DiscardFrame`. The PS5 source generator R335 carries *only* the recovery behavior in `vk_present_manager.h` and `.cpp`, not unrelated Android defaults or NCE/renderer settings.

## Behavior and ownership

- Healthy presentation returns on its first attempt, unchanged.
- Two consecutive surface-loss failures may recreate the surface/swapchain and recover on the third attempt.
- Three consecutive surface-loss failures exit the loop. `DiscardFrame(frame)` submits an empty graphics command that consumes the previously signaled `render_ready` semaphore under the existing `scheduler.submit_mutex` and signals `frame->present_done`, so this frame can be recycled with its existing fence lifecycle. This follows upstream instead of silently leaving its Vulkan synchronization primitives pending.
- Other Vulkan errors retain the existing throw/rethrow behavior. No queue capacity, shader cache, guest input, GPU execution ordering or normal-frame pacing changed.

## Evidence and limitations

`tools/check-ps5-vulkan-present-retry-liveness.py` verifies the exact pinned original by Git blob SHA, replays the entire real source generator, validates release semaphore/fence submission and compiles **the real extracted C++ `PresentManager::CopyToSwapchain` body** in a host mock, demonstrating expected original failure vs bounded success, recovered-after-2-faults, and unchanged first-try success. Tested with local pinned source; downloaded GitHub pinned source also supported. The generated production Vulkan translation unit passed `clang++-18 --target=x86_64-sie-ps5 -fsyntax-only` (nonfatal existing `-Wno-error-all` warning). CI source / native build run this test.

This is not evidence that FC27's specific menu-image stall is fixed, and does not address the remaining 30-FPS visual stutter, grass texture/HUD defects or game-side remapping behavior. No PS5 user test requested.
