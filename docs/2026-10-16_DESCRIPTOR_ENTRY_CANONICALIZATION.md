# Descriptor payload byte canonicalization (native-only)

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

## Source defect

The Vulkan descriptor ring uses a bytewise `std::memcmp` over
`DescriptorUpdateEntry` to decide whether an existing allocation can be reused.
This union stores multiple Vulkan structures, including 24-byte image descriptors
and address descriptors with a four-byte padding tail.

Assigning only the active Vulkan fields does not promise initialization of the
inactive union storage or structure padding. Optimized Clang builds can leave
different bytes there despite identical semantic descriptor fields. Such a false
difference triggers needless ring allocations and can increase pressure on
the already-documented conditional reuse / in-lock `scheduler.Finish()` path.

## Scoped change

For native descriptor-buffer writes only, `AddSampledImage`, `AddImage`,
`AddBuffer` (device address variant), and `AddTexelBuffer` (address variant)
zero the entire slot before assigning the active descriptor fields individually.
The regular Vulkan update-template path remains unchanged, as do the union size,
descriptor queue ABI, fences, scheduler, cache locks, and draw order.

The pinned source generator and the active header carry identical logic.
`tools/check-ps5-descriptor-entry-canonical-host.py` compiles the exact
methods extracted from the active header under Clang -O2 with ASan/UBSan,
poisons otherwise inactive bytes, and proves equal semantic descriptors produce
equal full-entry bytes and survive vector copying.

## Limits

This addresses false misses only; genuine descriptor changes can still trigger
the known in-lock GPU `Finish` fallback when the ring is exhausted. The isolated
host test proves deterministic entry bytes, not performance, game correctness,
GPU execution, or resolution of FC27 freezes, frame stalls or missing HUD.
No console build, release or hardware test is authorized.
