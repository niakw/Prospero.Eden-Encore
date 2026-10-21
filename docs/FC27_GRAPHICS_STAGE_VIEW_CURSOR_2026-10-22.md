# FC27 — precomputed graphics shader-stage view offsets

`GraphicsPipeline::ConfigureImpl` performs its texture-buffer binding under
`texture_cache.mutex` and `buffer_cache.mutex`. Previously every enabled
stage rescanned two immutable shader descriptor collections on **each draw**
just to advance `texture_buffer_it` past sampled and storage-image views.

`GraphicsPipeline` now records those two counts when the pipeline is
constructed from immutable `Shader::Info` descriptors. The draw reads the
cached counts instead of rescanning. The compile-time `Spec::has_images`
branch and all real texture-buffer bindings remain unchanged. Distinct
counts preserve the exact cursor behavior even when images are not enabled.

The source-extracted host fixture compiles the real constructor descriptor
count block and real draw-time pointer-advance block under -O0/-O2. It tests
96 deterministic five-stage combinations with variable descriptor counts
and checks both image-enabled and image-disabled specialization paths.
The pinned Vulkan regeneration oracle and fast/full CI require exact parity.

**Measured input:** the historical detailed FC27 trace recorded mean
1.758 us in the whole sampled bind-stage-descriptors phase; this is not
a measurement of the removed descriptor scans. No frame-time, HUD or
freeze improvement is claimed without same-binary console measurement.

Changed active owners: `vk_graphics_pipeline_cost.cpp`,
`vk_graphics_pipeline.h`; no changes to locks, memory ownership,
barriers, descriptor payload, image view IDs or draw order.
