# R391 — scaled Vulkan texture readbacks batched under PS5 memory pressure

Upstream: https://github.com/blackbearreloaded/ProsperoEden/commit/002c40cb794ccfb2787e245b6fa514572aac7cf3

## Source-level bug and fix

FC27 R384 continues to stutter around 30 FPS despite earlier scheduling repairs. Our actual compiled texture cache and its generator excluded image.HasScaled() from the GC prefetch. Every eligible scaled GPU-written image then fell back to a separate Cleanup DownloadMemory / runtime.Finish / SwizzleImage sequence. The recent upstream commit confirms the same slowdown on scaled render targets.

R391 removes ONLY the image.HasScaled() exclusion in both headless/vulkan_gc_downloads.inc and the byte-equivalent, full compiled vendor/encore-active Vulkan texture cache. Scaled images already use the same Image::DownloadMemory as Cleanup, which downscales to the expected CPU layout before readback.

The following existing safeguards are preserved: only dirty images; no aliased/overlapping or multisample textures; 40 images maximum and 32MiB staging maximum; oversized textures use the existing per-image fallback; same GPU Finish barrier and lifetime of deferred staging buffers; no changed guest coherency, queue ordering, GPU memory policy or pinned dependencies.

Upstream raised limits to 64 images/64MiB. R391 does NOT: unified PS5 memory capacity is still unqualified for that increase.

## Verification

- Host C++ mixed-GC sanitizer check PASS, including scaled textures, skip aliases/MSAA, and 40 x 1MiB scaled texture capacity.
- Host C++ prefetch buffer capacity/lifetime sanitizer check PASS.
- Host C++ GPU memory budget test PASS (200000 randomized/saturation cases).
- Entire pinned active Vulkan fork from source generator PASS, 40 files byte-for-byte equivalent.
- Boost headers are read from already vendored pinned Boost 1.90 on host rather than requiring local Homebrew Boost.
- CLT Mac test environment used SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk to avoid unsupported CLT27 .tbd linker metadata.

No native PS5 build or observed FPS improvement. This corrects one confirmed fallback-path inefficiency; HUD corruption and guest game-state stalls remain separate hypotheses.
