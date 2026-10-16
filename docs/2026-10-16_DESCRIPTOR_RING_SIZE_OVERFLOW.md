# Descriptor ring allocation-size overflow guard

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

The upstream `DescriptorBufferRing::CanAllocate` aligned an untrusted `VkDeviceSize` before comparing it with its fixed chunk capacity. Pinned `Common::AlignUp` uses unsigned arithmetic; for `UINT64_MAX` and 16-byte alignment the result wraps to zero. An impossibly large descriptor size can thus be misclassified as fitting a few-megabyte descriptor ring.

The native-only generated header rejects `size > chunk_capacity` before calling `AlignUp`. All requests of at most the finite ring capacity still follow the original aligned-capacity test. The immutable pinned upstream file is unchanged. The generator explicitly reproduces the guard.

`tools/check-ps5-descriptor-ring-overflow-host.py` compiles the verbatim guarded method alongside the pinned predicate and real pinned alignment function under C++20 ASan/UBSan. It reproduces original UINT64_MAX misclassification and checks ordinary, edge, disabled and oversized cases.

This protects invalid metadata. It does not move `scheduler.Finish`, alter descriptor reuse, cache locks, frame timing, Vulkan allocation behavior for valid requests or the console build/release. No claim is made that FC27 emits such a size or that its freezes, HUD or stutters improve.
