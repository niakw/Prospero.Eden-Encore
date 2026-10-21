# Graphics zero-descriptor queue — avoid under-lock worker drain

## Exact root
`vendor/sources/eden/src/video_core/renderer_vulkan/vk_update_descriptor.cpp:
UpdateDescriptorQueue::Acquire` implements `required_entries == 0` as
`DEFAULT_REQUIRED_ENTRIES = 0x400`. The old graphics call passed
`num_descriptor_entries` under the paired texture and buffer cache locks.
For a compiled pipeline with **exactly zero descriptors**, this could
check an artificial 1024-entry reservation and block in
`scheduler.WaitWorker` despite writing no entries.

## Reviewed fix
`vk_graphics_pipeline_cost.cpp::GraphicsPipeline::ConfigureImpl`
now uses `AcquireKnownEmpty` for the exact zero case. The method on the
maintained `vk_update_descriptor.h` copies precisely the state changes
of `Acquire` relevant to a no-descriptor draw:
`use_descriptor_buffer = supports_descriptor_buffer && requested` and
`upload_start = payload_cursor`. No cursor advance, worker wait,
descriptor discard, or texture/shader invalidation occurs.
Any nonzero graphics count and any other caller continue to call the
original `Acquire` and reserve as before.

The shader `NumDescriptorEntries` count is computed from the immutable
pipeline stage infos. Host test compiles the exact method and call-site
branch, exercises a nearly full ring, a real nonzero-overflow fallback
and a descriptor-buffer capability change, in O0/O2. Generator parity
and native fast-gate/preflight are required.

**Evidence boundary:** logical unnecessary-wait path proven in source;
actual frequency and time cost in FC27 not present in the historical
aggregate. The improvement is not a measured stutter or HUD fix.
