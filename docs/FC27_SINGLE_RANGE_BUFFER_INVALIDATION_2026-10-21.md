# FC27 — single-range buffer invalidation P0

**Source owner:** `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`
(copied into the real native video-core target by `headless/vulkan.cmake`).

After the batched `InnerInvalidation` change, two remaining single-range
entry points still locked the buffer cache for pages never registered:

- `RasterizerVulkan::InvalidateRegion` — conditional buffer-cache part
- `RasterizerVulkan::OnCacheInvalidation` — buffer-cache part

Both now use the conservative monotonic `BufferPages::NeverRegistered`
witness before locking. That witness returns false for unknown, broad,
out-of-range and previously-owned pages. Future first-use buffers remain
CPU-dirty by `WordManager` initialization, and `ChangeRegister<true>`
publishes the ownership witness before registering the page-table entry.
Texture writes, shader invalidation, query invalidation, and order stay
unchanged. No lock is skipped for a buffer with prior guest GPU ownership.

The exact native method bodies are extracted and compiled in
`tools/check-native-single-range-buffer-invalidation-host.py`. Cases
include never-owned and formerly-owned pages, texture-only pages,
zero-size guards, 128 KiB fallbacks, cache masks and unknown-coverage
fail-closed paths at O0 and O2. The pinned adapter oracle is updated
in `tools/prepare-vulkan-port.py`.

**Scope:** 1 active native C++ file, 2 methods, 2 host build variants.
A measured FPS/stutter gain cannot be claimed until a console A/B with
the same game state. This does not disable synchronization, skip texture
upload, or change JIT sparse selection.
