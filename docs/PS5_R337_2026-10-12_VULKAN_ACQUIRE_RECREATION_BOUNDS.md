# R337 — prevent infinite vkAcquireNextImageKHR swapchain recreation

Branch: `dev/ps5-sparse-jit`; pinned mirror commit `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Confirmed independent infinite loop

In the native Vulkan `PresentManager::CopyToSwapchainImpl`, even after R335 bounded **outer** `VK_ERROR_SURFACE_LOST_KHR` retries, the **inner** loop still reads `while (swapchain.AcquireNextImage()) { RecreateSwapchain(frame); }`. `Swapchain::AcquireNextImage` returns `true` on each `VK_SUBOPTIMAL_KHR` or `VK_ERROR_OUT_OF_DATE_KHR`, after updating `is_suboptimal/is_outdated`. The adjacent `Swapchain::Create` clears these flags when recreating. If acquisition keeps returning one of those recoverable statuses, it can spin/rebuild a swapchain indefinitely, monopolizing the background present thread and preventing frame handoff. R335's limit alone cannot stop the inner loop.

## Narrow PS5 correction

The exact pinned-source generator now replaces this with a loop permitting **at most 3 acquisitions per invocation**, i.e., two internal recreations. Persistent acquisition failures throw `vk::Exception(VK_ERROR_SURFACE_LOST_KHR)` and enter the existing R335 bounded **outer** recovery flow and `DiscardFrame(frame)` fence/semaphore cleanup after three outer attempts. Normal first-try acquisition is unchanged; two transient outdated/suboptimal acquisitions can recover on the third. No new per-frame clocks, GPU waits, guest input changes or general queue changes.

## Regression evidence

`tools/check-ps5-vulkan-swapchain-acquire-bounds.py` pins exact Vulkan source via Git blob SHA and replays the production generator. Its C++ host compilation extracts the real old and new acquisition-loop bodies. Under a persistently invalid swapchain, old code exceeds 16 attempts (caught by an artificial test watchdog), new code throws after 3 acquisitions and 2 recreations; one-try healthy and two-recovery scenarios also pass. The fully generated `vulkan_present_manager.cpp` passed `x86_64-sie-ps5 -fsyntax-only` with the existing SDK warning. Both CI workflows include the gate; full PS5 native application build remains required.

This fixes a demonstrable potential hang in surface acquisition, not proof that the observed FC27 frozen controller menu resulted from this path. FC27 texture corruption, menu button reassignment and 30-FPS perceived stutters remain open. User console testing is not requested.

## Interpreting the old 30-FPS traces

`RendererVulkan::Composite()` calls `render_window.OnFrameDisplayed()` through a `SCOPE_EXIT`, **before** the Vulkan presentation worker necessarily completes `CopyToSwapchain` and `Swapchain::Present()`. This callback also runs when a composition is skipped or aborted early. Thus the existing `EDEN_VULKAN_FRAME` / HUD counter measures attempted/completed *guest composition callbacks*, not guaranteed unique displayed frames or confirmed `vkQueuePresentKHR` success. Earlier descriptions saying the stuck FC27 menu was definitely presenting 30 new images per second were too strong. Logs support continuing GPU and IPC work with ~30 composition callbacks/s, but do not prove frame-content changes or physical display pacing. Do not use this number alone to close visual-freeze reports.
