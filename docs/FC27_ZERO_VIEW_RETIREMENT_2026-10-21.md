# Zero-view texture retirement: avoid irrelevant cache scans/flushes

**Native compiled owner:** `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h`

`DeleteImage` and `InvalidateScale` can pass `image.image_view_ids`
to both `RemoveImageViewReferences` and `RemoveFramebuffers` even when an
image was created, reused or retired with no image-view references.
The original implementation scanned each active channel's descriptor map,
then executed `runtime.FlushDeferredClear` and scanned every cached
framebuffer, despite an empty view list being unable to match any of them.

Two PS5-specific, early `removed_views.empty()` guards now avoid those
unproductive operations. **When one or more views exist**, both functions
execute their entire original deletion logic and preserve deferred-clear
flush ordering, framebuffer serial invalidation, view eviction and delayed
resource destruction. No GPU cache lock is removed, and neither readback
nor active texture/attachment invalidation is skipped.

Host test `check-ps5-empty-image-view-retirement-host.py` compiles the
exact selected functions at O0/O2 and checks empty/no-op retirement,
nonempty multi-channel removals, framebuffer serial invalidation, and
repeat nonempty deletions. Pinned source regeneration and full native
CI preserve parity.

This change targets a previously unmeasured side cost of texture-cache
retirement; FC27 logs do **not** contain a call frequency for these
empty-view paths. No FPS, HUD or jersey recovery claim is justified until
paired console measurements establish one.
