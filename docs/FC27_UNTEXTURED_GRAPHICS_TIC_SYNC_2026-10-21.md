# FC27 — graphics descriptor synchronization without sampled images

**Selected owner:** `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp`,
`GraphicsPipeline::ConfigureImpl`. The native CMake target copies this owner
through `headless/vulkan.cmake`, not the historical source oracle.

Previously, every graphics draw executed
`texture_cache.SynchronizeDescriptors(false)` under
`buffer_cache.mutex` and `texture_cache.mutex`, even when its compiled
shader stages declared **zero** image, texture buffer or image buffer entries.
The cache synchronization reads guest TIC/TSC tables but these shaders never
use those tables in their descriptor bindings.

The existing immutable `num_image_elements` count includes all four descriptor
categories. For zero entries, skip only this descriptor-table synchronization;
a later textured draw still runs the original synchronization. Render-target
refresh, guest write invalidations, shader invalidation, descriptor queue,
GPU draw recording and feedback checks remain in their original order and
with their existing locks.

A host fixture compiles the extracted native guard at O0/O2, verifies the
zero/nonzero paths, confirms the constructor counts all categories and
asserts the subsequent GPU work is not moved. The pinned generator and
native C++ source are modified together.

**Performance scope:** a real reduction in TIC/TSC table checks for
texture-free pipelines. Historical FC27 logs do not provide their frequency,
so no FPS or late-frame improvement is yet quantified. This change does
not address the intermittent missing HUD/jersey textures directly.
