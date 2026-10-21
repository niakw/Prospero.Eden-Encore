# FC27: immutable no-image graphics stage classification

**Source owners**: maintained `vk_graphics_pipeline_cost.cpp`,
`vk_graphics_pipeline.h`, their pinned Vulkan regeneration oracle.

The detailed FC27 guest trace assigned approximately 1.76 microseconds per
sampled draw to the *whole* stage-descriptor binding phase. This is not a
measurement of this individual helper. Previously every enabled stage
called `PushImageDescriptors` under the paired GPU buffer/texture locks,
even when no image/texture-buffer descriptors existed.

At pipeline creation, copy a single immutable per-stage flag from all four
descriptor category collections. At draw time, keep
`buffer_cache.BindHostStageBuffers` and render-area constant selection in
place, but skip `PushImageDescriptors` if *all four* collections are empty.
Nonempty buffer-only stages still call it, preserving the advancement of the
shared descriptor-view cursor across shader stages. Sampled and writable
images retain their original binding and rescaling logic.

The host fixture compiles the native constructor classification and the
actual extracted stage lambda at O0 and O2 and checks empty, texture-buffer,
image-buffer, sampled-image and storage-image configurations. The native
generator parity gate requires an exact source match.

This reduces descriptor scanning in texture-free shader stages; actual
frequency and FC27 frame-time impact remain **unknown** until console tests.
No changes to cache locks, fence order, guest invalidation, HUD views, JIT,
descriptor lifetimes or Vulkan command sequencing.
