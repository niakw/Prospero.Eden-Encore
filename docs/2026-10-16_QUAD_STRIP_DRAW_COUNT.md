# Native quad-strip draw count: prevent unsigned underflow

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

`MakeDrawParams` converted quad strips with
`(num_vertices - 2) / 2 * 6` using `u32` arithmetic. For zero or one
vertex, subtraction wraps to a very large number, creating a giant
`vkCmdDrawIndexed` request rather than an empty primitive.

The native renderer and pinned generator now use
`num_vertices >= 2 ? (num_vertices - 2) / 2 * 6 : 0`.
`BindQuadIndexBuffer` additionally reuses its existing null-buffer
binding for all draws with fewer than four vertices; those cannot form
a complete quad and must not trigger a zero-byte LUT allocation.
Normal strips, quad arrays, triangle paths, base-vertex handling,
render-pass state, descriptor queues and Vulkan synchronization are unchanged.

`tools/check-ps5-quad-strip-draw-count-host.py` extracts the production
function into a C++20 Clang ASan/UBSan witness. It checks 256 consecutive
counts including 0, 1, 2 and 3, both direct/indexed inputs, and verifies
the existing non-strip topology counts are unchanged. Source and generator
guards verify incomplete quad draws never reach LUT allocation.

No console build or release is requested. This is a demonstrated arithmetic
defect, not an established cause of any particular title's freeze or HUD issue.
