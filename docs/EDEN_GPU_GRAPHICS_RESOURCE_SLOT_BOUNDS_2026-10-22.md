# Native graphics resource-slot bounds — 22 October 2026

## Observed defect

The selected `BufferCache::BindGraphicsStorageBuffer` and
`BindGraphicsTextureBuffer` performed a u32 mask shift and indexed per-stage
fixed arrays without rejecting out-of-range shader descriptor indices.
The channel reserves exactly 16 graphics storage buffers and 32 graphics
texture buffers per stage, across five stages. Both compute equivalents
already rejected oversized buffer-slot indices.

An SSBO index >=16 overwrote memory past the stage array; a TBO index
>=32 caused an undefined-width bit shift and a possible out-of-bounds
write. Either error could corrupt adjacent GPU binding state. This is a
concrete safety defect; it is not yet traced to a specific FC27 image.

## Maintained fix and regression

Check stage and descriptor-slot bounds before reading or modifying ANY
enabled/written/image masks or per-stage binding arrays. Valid indices and
the existing driver storage-binding limit behave unchanged.

`tools/check-native-graphics-buffer-slot-bounds-host.py` compiles
the real selected C++ methods at -O0/-O2 with ASan/UBSan and tests
the valid endpoints, both first and far out-of-range indices, invalid
stages and dynamic host-limit accounting.

Both independent R437 reconstruction oracles include precisely these
two native changes. The source remains solely under
`vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h`.
No speculative JIT/cache-lock policy is enabled. There is no claim of
improved frame pacing or repaired FC27 jersey/HUD graphics until console
measurement.
