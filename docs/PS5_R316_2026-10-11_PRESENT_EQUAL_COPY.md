# R316 — PS5 native Vulkan same-extent present copy

Branch `dev/ps5-sparse-jit`. Pinned Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Reason

Pinned `PresentManager::CopyToSwapchainImpl` chooses `vkCmdBlitImage(...VK_FILTER_LINEAR)` whenever blit is supported, including when frame and swapchain are already the same size. Its `RecreateFrame` allocates the frame in exactly `swapchain.GetImageFormat()`, the same format as the destination. With **matching extents and identical formats**, this filtered blit is not required for resizing or conversion.

## Change

The `tools/prepare-vulkan-port.py` production source adapter now uses `vkCmdCopyImage` if the PS5 Vulkan frame dimensions exactly equal the swapchain extent. It retains the original `vkCmdBlitImage(VK_FILTER_LINEAR)` path for different extents when blit is supported, and retains the original no-blit fallback. `#ifdef PS5_NATIVE` leaves upstream/non-PS5 identical. No change to image barriers, command submissions, acquire/present, 512-draw safety cap, shader scaling, or presets.

This is a small and conditional copy-path optimization, **not** a confirmed improvement to FC27's terrain sharpness. A 1440p output to a 4K VideoOut **still** uses linear blit, which may compound other resampling. Runtime frame pacing remains unverified. Do not automatically force output 4K, which would increase the render/resize cost.

## Regression

`tools/check-ps5-present-equal-copy.py` SHA-checks the exact upstream present source, extracts the production adapter from Python AST, verifies same-format source/destination construction, compiles the actual changed C++ conditional against mock Vulkan command calls, and checks 1080/1440→4K blit, 4K→4K copy, alternative extents, no-blit fallback and original upstream behaviour. Registered in core preflight and native build. No native build launched in this source-only commit.
