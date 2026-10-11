# R331 — Release raw Vulkan image views before their backing images

Single canonical branch: `dev/ps5-sparse-jit`; Eden mirror pinned commit `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`, guest compositor source Git blob `14935f92bb450973e85237fed52f8dea6d172688`.

## Source-verified lifetime fault

The pinned `src/video_core/renderer_vulkan/present/layer.cpp` constructs each `raw_image_views[i]` by passing `*raw_images[i]` to Vulkan's image view constructor. Its `Layer::ReleaseRawImages()` waited for associated `resource_ticks`, but cleared `raw_images` **without clearing `raw_image_views` first**. The old VkImageViews remained live until a later overwrite in `CreateRawImages()` or member destruction, after their backing `VkImage` handles were destroyed. These are separate Vulkan resources; an image must outlive all its views. GPU tick completion alone does not rectify the invalid object-destruction order. The method runs during full reallocation (resize/format switch) and shutdown, and had not been addressed by R327–R330.

## Narrow correction

In PS5's generated `vulkan_present_layer.cpp`, within `ReleaseRawImages()` and **after** the original `scheduler.Wait(tick)` loop, call `raw_image_views.clear()` **before** `raw_images.clear()`; keep `buffer.reset()` after both. The old layer code's other paths and native behavior remain unchanged. The R330 stride-only fast path does not call `ReleaseRawImages` and retains the existing views and raw image resources, so it is unaffected.

No added per-frame GPU waits, no shader bypass, no changes to texture precision, FSR quality, present filters, game memory layout, FPS caps or cache budgets. This is a resource-lifetime correctness repair on the existing reallocation/shutdown path.

## Qualification

`tools/check-ps5-vulkan-raw-view-lifetime.py` SHA-checks the pinned **actual** Eden Layer source, extracts and applies all production generator edits for the Vulkan layer, and host-compiles/runs the *actual* `Layer::ReleaseRawImages()` C++ method with RAII `Image`/`ImageView` mock wrappers that record object dependencies. Original branch fails when a backing image is freed while its view is still live; patched method passes, keeping GPU tick waits ahead of any destruction and covering repeated release. Existing R328/R330 C++ source fixtures pass with the new generator output. The native `x86_64-sie-ps5` source syntax and complete CI build are independent qualification gates; gameplay quality needs on-console evidence before any claims.
