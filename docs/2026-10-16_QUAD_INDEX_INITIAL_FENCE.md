# Avoid a first-use full GPU fence for quad-index LUTs

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

The active Vulkan `QuadIndexBuffer::UpdateBuffer` used to call
`scheduler.Finish()` on its *first ever* allocation as well as on each
subsequent capacity growth. The first allocation starts with default-initialized
`vk::Buffer buffer{}` (a null Vulkan handle). There is no previous LUT buffer
to protect from in-flight work, so completing all queued GPU commands is
unnecessary on that first call.

The native Vulkan source initially conditioned the *existing* Finish on
`if (buffer)`. It now also tracks the last GPU tick when it uploads or binds
the index buffer. The original Finish is required only when that last-use tick
is **not yet completed** (`!scheduler.IsFree(last_use_tick)`).

`Scheduler::IsFree()` reads the known-completed GPU semaphore tick without
waiting; if the known completion is stale the existing Finish remains. This
skips unnecessary full-device sync when the prior LUT is definitely idle,
while preserving the fence for an in-flight resize. No draw, index generation,
copy barrier, cache lock or scheduler ordering is changed. Both quad and
quad-strip LUTs use this same class.

`tools/check-ps5-quad-index-initial-fence-host.py` asserts the actual source
placement and pinned generator adapter, the Vulkan wrapper's null-handle
semantics, and executes the exact extracted condition in a Clang ASan/UBSan
fixture. The fixture distinguishes first allocation, unchanged capacity, growth of an
in-flight buffer, growth after a completed last-use tick, and a new binding
recorded on a later tick. Full native-generator parity is enforced by the existing
CI preflight.

This is narrow: the source still has GPU waits under guest cache locks for
**later quad-index buffer resizes whose GPU ticks are still in flight** and conditional graphics descriptor-buffer
ring reuse. No claim is made about FC27, which may never use quad topologies.
No console build, release or hardware test is requested.
