# Clear scissor signed underflow at INT32_MIN

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

In the native rasterizer's clear-path `clamp_rect_to_render_area`,
a negative scissor offset was negated directly as an `s32` to compute the
amount of a rectangle lying outside the render area. For `INT32_MIN`,
`-offset` overflows signed 32-bit arithmetic and causes undefined behavior.
The result may be incorrect scissor clipping or a build-dependent fault.

The native code and pinned source generator now widen the signed offset to
`s64` **before** negating it. The value then fits safely in `u32`,
including the magnitude of `INT32_MIN`. No Vulkan synchronization,
framebuffer state, pipeline selection or valid rectangle calculation changes.

The source-extracted host test compiles the production clipping lambda with
Clang C++20, AddressSanitizer and UndefinedBehaviorSanitizer. It evaluates
230,400 rectangle/area combinations, including `INT32_MIN`, `INT32_MAX`,
zero extents and oversized rectangles, and compares with an independent
64-bit intersection oracle. The full pinned/active generator parity preflight
also runs in CI.

No console build, release or hardware test is requested. This fixes a
reproducible integer arithmetic defect; it is **not** evidence that
a particular title's HUD, stutters or freezes are resolved.
