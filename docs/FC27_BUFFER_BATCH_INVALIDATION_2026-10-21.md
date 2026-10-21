# Exact CPU/GPU invalidation-target correction — 21 October 2026

**Owned active source and inactive mirror:**\n`vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp`\nremains byte-identical for the three rasterizer invalidation methods;\nthis experimental bridge is not selected in the normal release.\n\n**Owned source:** `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`,
`RasterizerVulkan::InnerInvalidation`. CMake builds the tracked active file
via `headless/vulkan.cmake`; the **historical generation oracle** in
`tools/prepare-vulkan-port.py` carries the byte-identical change.

**Observed:** FC27 detailed trace reported over 1 million blocked buffer
cache acquisitions and 9.31 seconds of summed waiting across 232 windows.
This cannot be assigned exclusively to `InnerInvalidation` without a
per-function runtime counter. It does justify avoiding redundant holds,
given the preexisting safe page-ownership mechanism.

**What changed:** the buffer half of the batched guest invalidation now
checks `Eden::BufferPages::NeverRegistered` before taking
`buffer_cache.mutex`. For a mixed batch, it still holds the original
mutex while processing all formerly owned/unknown buffer pages in source
order; it omits only definitely never-owned buffer pages. The texture half,
query invalidation, shader invalidation, and their original order remain.

**Why a future new buffer does not lose its first CPU upload:**
`BufferCache::ChangeRegister<true>` publishes
`BufferPages::Mark` *before* publishing into `page_table`.
`WordManager` initializes every new page's CPU bit dirty, so a write to
a never-buffer-owned page need not pre-create a tracker merely to mark it
dirty. Previously registered pages retain their write and lock path.
Ranges >64KiB, out-of-range and missing monotonic coverage keep the
old full path.

**Evidence and boundary:** `tools/check-native-batched-buffer-invalidation-host.py`
extracts and runs the *actual* selected method with faithful cache/owner
doubles, checking never-registered, mixed, formerly registered, large
fallback, independent texture paths and query/shader preservation at O0/O2.
The existing Vulkan fork parity test independently verifies generator /
selected active source equivalence. This is a source-backed lock-contention
reduction for eligible batches; it is **not yet a measured FPS gain**.
The actual fraction of guest invalidations with wholly never-buffer-owned
pages remains to be measured on console.

**Status accounting:** code modified=1 selected native translation unit;
reviewed=1 exact method; host regression=pending CI; native build=pending;
console microstutter/HUD/jersey outcome=unverified. Do not fold this into
a false `429 optimized` count. All-on DEV / sparse JIT remains unchanged.
