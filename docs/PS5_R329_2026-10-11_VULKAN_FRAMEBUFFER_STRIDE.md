# R329 — Revalidate Vulkan raw framebuffer staging size when stride changes

Canonical branch: `dev/ps5-sparse-jit`; pinned Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`, presentation source Git blob `14935f92bb450973e85237fed52f8dea6d172688`.

## Source-verified memory sizing fault

`Layer::RefreshResources` in the pinned Vulkan compositor reused its per-frame raw staging allocation whenever guest framebuffer `width`, `height` and `pixel_format` matched. It did **not** compare `framebuffer.stride`, although all these downstream operations use that property:

- `Layer::CalculateBufferSize()` returns `stride * height * bytes_per_pixel * image_count`, determining the exact staging allocation size.
- `Layer::GetRawImageOffset()` offsets each in-flight image slot by `stride * height * bytes_per_pixel`.
- `Layer::UpdateRawImage()` calls `mapped_span.subspan(image_offset, linear_size)` and uses `framebuffer.stride` for the guest tiling calculation.
- The pinned Vulkan allocator returns the host mapped span with **exactly `ci.size` bytes**, independently of any larger memory-page or heap reservation (`vulkan_memory_allocator.cpp`).

If a guest producer changes the row stride while retaining the same pixel width/height/format, the old preflight returns early with a staging allocation and image slot offsets sized for the previous stride. An increase can exceed the mapped staging span; a decrease can carry stale offsets. This is a concrete sizing mismatch, **not** proof that FC27 changes stride in the supplied session.

## Narrow correction

In the existing PS5-native `vulkan_present_layer.cpp` derivation, require `buffer.Mapped().size() == CalculateBufferSize(framebuffer)` alongside the original dimensions, pixel format and existing raw-image checks before reuse. If the size differs, the original `RefreshResources` reallocation path runs, including the R328 antialias destruction guard and original raw-image resource ticks. No new allocation or wait occurs when the stride is unchanged. This change applies only to the generated PS5 Vulkan unit; upstream Eden, OpenGL and other platforms remain unchanged. No extra source header field or divergent mapping cache is introduced.

## Reproduction and qualification

`tools/check-ps5-vulkan-stride-reallocation.py` SHA-verifies pinned `present/layer.cpp`, extracts and applies **all three** actual production source replacements for the generated file, checks the pinned allocator's `ci.size` mapping contract, then host-compiles/runs the real `Layer::RefreshResources()` method. Tests initial allocation, unchanged draw, larger row stride with identical visible extents, repeat frame, smaller stride, resize, and pixel-format change. The original source fails precisely at the increased-stride test; patched code passes all scenarios. The R328 test still isolates the two earlier antialias lifetime changes, and the R329 test replays their combined real generator alongside the stride fix. The actual generated `vulkan_present_layer.cpp` also passed `x86_64-sie-ps5` cross-target C++ `-fsyntax-only`.

CI regression workflows both include the new host C++ proof; native PS5 compile, link, staging, packaging and any eventual gameplay-quality claim require their separate gates. Do not assert FC27 grass/HUD or performance has been fixed from source checks alone.
