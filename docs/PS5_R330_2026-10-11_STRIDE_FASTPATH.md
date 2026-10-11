# R330 — Stride-only framebuffer upload: preserve AA and raw Vulkan image resources

Canonical: `dev/ps5-sparse-jit`; Eden source pinned at `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Why R329 needs this follow-up before console testing

R329 correctly detected a guest framebuffer `stride` change by comparing its mapped staging-buffer size to the required capacity. Without that guard, `Layer::UpdateRawImage()` can index beyond the stale buffer for a pitch increase, even at unchanged visible width/height/format.

But the R329 reallocation initially fell through `Layer::RefreshResources`' full resize path. With FXAA/SMAA active, R328 correctly waits for all GPU work before **destroying the old antialias pass**, and then recreates raw images, descriptors and staging resources. On a `stride`-only change, however, the AA pass' width/height/format have NOT changed, nor have the raw image formats or dimensions. Destroying them is needless and could itself introduce new game stutters if a title alternates pitch frequently.

## Change

In the generated PS5-only `vulkan_present_layer.cpp`, the full reuse check still compares the staging buffer's exact mapped size to `CalculateBufferSize(framebuffer)`.

If only `stride` differs, **before** the full-resize R328 path:

1. Wait each current `resource_ticks` via the existing `scheduler.Wait(tick)`, exactly as upstream `ReleaseRawImages` does before freeing any old raw allocation.
2. Call `CreateStagingBuffer(device, framebuffer)` to replace the existing upload buffer with the newly required size (the wrapper's move assignment retires its prior allocation).
3. Return with the current `raw_images` and `raw_image_views` and the existing FXAA/SMAA and FSR resources intact.

Consequently pitch-only changes do not call `scheduler.Finish()` or `device.WaitIdle()`; unchanged images still return without waits or allocations. **Real width, height, pixel-format or AA mode transitions** continue through the full R328 resource-lifetime safeguard. Original non-PS5 Vulkan code is untouched. No frame drop, shader disable, synchronization bypass, extra JIT cache, or GPU-queue enlargement.

## Tests

`tools/check-ps5-vulkan-stride-reallocation.py` SHA-verifies the original pinned C++ source, replays all actual generator substitutions, verifies the VMA allocator's exact `ci.size` mapped span and compiles the resulting real `Layer::RefreshResources()` into a test harness. A hot AA variant survives pitch 704→768→736 without global idle or AA reconstruction, with per-slot tick waits before replacing upload memory; identical pitch does zero work; actual resize frees AA only after an idle drain. The original Eden method fails its increased-stride bounds check. The R328 source fixture independently still tests FXAA↔SMAA lifetime. Generated actual `vulkan_present_layer.cpp` passes PS5 `x86_64-sie-ps5` syntax check.

This is a targeted prevention of **new** stalls induced by the R329 safety patch. It does not prove what stride FC27 uses or that its in-game missing HUD, pitch pixelation or frame pacing will be resolved. Native CI, staging and on-console validation are separate.
