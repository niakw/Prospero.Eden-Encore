# FC27 — pipeline-aware first descriptor preflight

**Active owners:** `vulkan_rasterizer.cpp::RasterizerVulkan::PrepareDraw`,
`vk_graphics_pipeline.h::GraphicsPipeline::HasDescriptorEntries`.
The earlier no-descriptor queue fix avoided `Acquire(0)`'s 1024-entry
fallback under guest cache locks, but the **earlier**
`PreflightGuestDraw` was still unconditionally waiting before the
pipeline was even selected, so it could trigger the same unnecessary
worker drain.

Now the rasterizer selects the graphics pipeline *before* the ordinary
queue preflight, and performs the preflight only if its immutable
shader-derived descriptor count is nonzero. If the worker actually drains,
the rasterizer flushes pending guest memory remaps and reselects the
pipeline before entering the unchanged large-draw/ring/scratch preflights
or paired guest cache lock. Null results still record the original drop.

`tools/check-ps5-graphics-pipeline-aware-preflight-host.py` extracts the
selected native path and executes zero-descriptor, nonzero, overflow,
pipeline-changed, lost-pipeline and no-overflow cases at O0 and O2.
The pinned source transformation and native header are updated together.

**No CUDA/Vulkan synchronization is bypassed for descriptor-using draws.**
Texture/jersey/HUD correctness still requires console validation.
The historical FC27 logs cannot quantify how many zero-descriptor draws
reached an almost-full descriptor queue, so no FPS gain is claimed.
