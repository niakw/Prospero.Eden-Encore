# Drain guest memory invalidations before DrawTexture cache lookup

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

The native Vulkan `DrawTexture()` used `FlushWork()` followed immediately
by acquiring `texture_cache.mutex`, `SynchronizeDescriptors(false)` and
`UpdateRenderTargets(false)`. Unlike the ordinary draw, clear and compute
paths, it did not call `gpu_memory->FlushCaching()` before resolving textures
and framebuffers.

`MemoryManager::FlushCaching()` consumes queued page-map invalidations,
then invokes `RasterizerVulkan::InnerInvalidation()`. The latter takes
`texture_cache.mutex` and invalidates texture pages and cached pipeline
bindings. It must run **before** `DrawTexture` locks the texture cache:
calling it inside the existing critical section would deadlock.

The pinned Vulkan adapter and active renderer now place the existing
invalidation drain immediately after `FlushWork()`, before the texture
lock and all sampled-image/render-target lookups. No draw order, cache
locking, GPU fence, descriptor buffer, sampling or blit parameters change.

A source-backed Clang ASan/UBSan test extracts the exact pre-lock sequence,
verifies the native/pinned generator parity and production invalidation
lock ownership, then exercises pending and empty invalidation queues
without recursive locking.

This is a source-level cache coherency correction. It does not establish
that a particular game uses the DrawTexture path, that stale texture
lookups occurred on the console, or that the HUD/freeze symptoms are fixed.
No console build, release or hardware tests are requested.
