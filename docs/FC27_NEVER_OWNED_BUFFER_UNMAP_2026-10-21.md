# Native CPU unmap: skip impossible buffer-cache invalidation

**Root**: `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp::
RasterizerVulkan::UnmapMemory`; experimental source parity:
`vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp`.

Earlier source coverage eliminated the never-owned lock on
`RasterizerVulkan::OnCPUWrite`, `InvalidateRegion`, and
`OnCacheInvalidation`. `UnmapMemory` still unconditionally acquired
`buffer_cache.mutex` and invoked `BufferCache::WriteMemory`, even when
no GPU buffer had ever been registered at the unmapped CPU pages.

Reuse the existing monotonic `Eden::BufferPages::NeverRegistered`
witness. It fails closed for large/unknown/formerly-owned spans; owner
registration publishes the bit before insertion into `page_table`, and
a new buffer starts CPU-dirty in `WordManager`. Unmaps of formerly owned
buffers therefore always take the original lock and invalidate their GPU
dirty/download tracking. No skip occurs based on currently unregistered
state alone.

Texture `UnmapMemory` and shader `OnCacheInvalidation` retain their
order and behavior. The exact native function is compiled at -O0/-O2 with
never-owned, previously owned, image-only, oversized, and globally
unknown page-map cases. The DEV bridge and pinned codegen oracle are updated
together and checked for parity.

**Evidence boundary**: the original FC27 logs show severe buffer-cache
contention but do not identify the number of `UnmapMemory` calls. This
removes a known unnecessary mutex acquisition; measured FPS improvement
or HUD recovery is not claimed.
