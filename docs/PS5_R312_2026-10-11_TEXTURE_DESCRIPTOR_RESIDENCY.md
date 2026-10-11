# R312 · FC27 PS5 texture-descriptor residency safeguard

## Motivation and evidence

On R310, FC27 showed field shimmer/pixelation in motion, jersey texture corruption,
and intermittent scoreboard/HUD; session #1 also emitted:
`video_core/texture_cache/format_lookup_table.cpp:276 texture format=0 srgb=false components={0 0 0 0}`.

This is an invalid Switch TIC format: pinned `Tegra::Texture::TextureFormat` starts at
`R32G32B32A32 = 0x01`. The pinned upstream `PixelFormatFromTextureInfo` ultimately
returns `A8B8G8R8_UNORM` on unknown format rather than refusing the descriptor.

Pinned Eden `src/video_core/texture_cache/util.cpp::IsValidEntry` accepts a
descriptor if the first GPU address is mapped, or (when the first address is not
mapped) if `GpuToCpuAddress(addr, guest_size)` succeeds. The **range overload
returns the first mapped page anywhere in the range** (`memory_manager.cpp`);
it does **not** prove the leading page is mapped or the texture fully resident.
Thus an unsparse descriptor whose first page is absent can pass because a
later page happens to be mapped.

## PS5-only R312 change

`headless/backports/eden-ps5-texture-descriptor-residency.patch`:

- Reject `TextureFormat(0)` at `IsValidEntry` before `ImageInfo` or a
  Vulkan image/view allocation; never falsely reinterpret it as RGBA8.
- If the leading GPU page is not mapped, reject **non-sparse** textures
  rather than treating any later mapped page as valid.
- Preserve upstream partial-mapping acceptance for `is_sparse != 0`,
  where holes in the leading GPU pages can be intentional.
- Keep successful formats, addresses and sparse texture behavior unchanged.
  This does not touch cache mutexes, GPU barriers, shader compilation,
  image staging, driver memory pools or GPU dispatch cadence.
- Preserve non-PS5 upstream source semantics with `#ifdef PS5_NATIVE`.

Safety: Rejecting an invalid TIC means the shader binds a null texture
instead of sampling an arbitrary potentially stale fallback image.
This is **not proof that missing HUD/jersey textures will reappear**; the
underlying producer of an invalid descriptor still needs discovery. Other
gaps and genuinely unmapped mip tails may require further GPU/guest tracing.

## Reproduced validation

`tools/check-ps5-texture-descriptor-guard.py` SHA-verifies the exact pinned
upstream Git blob, applies the actual production patch with `git apply
--check`, extracts `IsValidEntry`, and compiles/executes it in both
`PS5_NATIVE` and upstream configurations. Cases: defined/undefined format,
zero/oversized address, first page present, only later page present for
normal and sparse textures, no pages present. Both core source-preflight and
full native build run this check.

The R310 three-run data show sporadic `FillImageViews` critical-section
spikes to 11.36 ms (session 2), 4.75 ms (session 3), and 3.01 ms (session 1)
on the 1/16-draw detailed sample. The sampled phase is nested in
`GraphicsPipeline::ConfigureImpl` under texture+buffer cache mutexes.
At many 30-FPS intervals the GPU owner may block CPU guest writes without
visible present jitter; the measured 5-second FPS is NOT game simulation
cadence. Do not remove mutexes or assume a 512-draw dispatch cadence will
solve the measured JIT stalls.

## Other graphics chain finding

A potential persistent PS5 swapchain recreation caused by the 1440p game
frame and fixed 4K VideoOut was checked and **ruled out** in the pinned source:
`Swapchain::Create` records the *requested* `width`/`height`, used by
`GetWidth()/GetHeight()` for the recreate check; the actual 4K surface is
stored separately in `extent`. So the ordinary 1440p → 4K blit is still
present, but the width comparison does not recreate every frame.

## Explicitly remaining

- A true shader/texture *completeness* or feedback loop tracing for HUD and
  uniforms; a valid first mapped page can coexist with later holes.
- FC27 stutter from JIT churn, async shader fallback, texture-preparation
  spikes, GPU dispatch scheduling and presentation frame duplication.
- Source parity and correctness tests are not a substitute for PS5 game testing.
  User ended tests for the night. Do not ask for another now.
