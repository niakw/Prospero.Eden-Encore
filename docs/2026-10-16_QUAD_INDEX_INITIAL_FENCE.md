# Avoid a first-use full GPU fence for quad-index LUTs

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

The active Vulkan `QuadIndexBuffer::UpdateBuffer` used to call
`scheduler.Finish()` on its *first ever* allocation as well as on each
subsequent capacity growth. The first allocation starts with default-initialized
`vk::Buffer buffer{}` (a null Vulkan handle). There is no previous LUT buffer
to protect from in-flight work, so completing all queued GPU commands is
unnecessary on that first call.

The native Vulkan source now conditions the *existing* Finish on `if (buffer)`.
Every resize with an existing buffer still uses the exact original fence before
replacing it. No draw, index generation, copy barrier, later lifetime guard,
cache mutex or scheduler ordering is changed. Both quad and quad-strip index
LUTs use this same class.

`tools/check-ps5-quad-index-initial-fence-host.py` asserts the actual source
placement and pinned generator adapter, the Vulkan wrapper's null-handle
semantics, and executes the exact extracted condition in a Clang ASan/UBSan
fixture. The fixture distinguishes first allocation, identical/lower count
and subsequent growth. Full native-generator parity is enforced by the existing
CI preflight.

This is narrow: the source still has GPU waits under guest cache locks for
**later quad-index buffer resizes** and conditional graphics descriptor-buffer
ring reuse. No claim is made about FC27, which may never use quad topologies.
No console build, release or hardware test is requested.
