# Conditional descriptor-ring reuse: remaining locked GPU wait

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.
Status: source-level hazard reproduced; **not** an observed FC27 event.

## Why the guaranteed-only preflight is incomplete

`GraphicsPipeline::DescriptorRingPreflightSize()` returns zero when the
pipeline's previous descriptor-buffer generation and entry count match the
current values. This is intentionally conservative: the actual guest
descriptor payload cannot be compared until the caches are locked.

Inside `GraphicsPipeline::ConfigureDraw()`, the payload can differ while
its count remains identical. The existing `std::memcmp` then rejects the
old allocation and calls `DescriptorBufferRing::Allocate()`. If the
current ring chunk is exhausted and there are no additional chunks,
`Allocate()` calls `scheduler.Finish()` while `PrepareDraw()` still
holds the guest buffer-cache and texture-cache mutexes.

The source-extracted Clang ASan/UBSan host witness at
`tools/check-ps5-descriptor-conditional-reuse-host.py` constructs:
- equal generation and descriptor count, but different descriptor bytes;
- a full last ring chunk;
- a zero-size preflight and a later allocation under both locks.

It confirms that the original fallback calls `Finish` while locked, and
also verifies the successful pre-drain path when generation mismatch
makes a new allocation certain.

## Engineering trade-off

Finishing the GPU unconditionally whenever the ring is full would avoid
this particular locked wait, but would force submission/completion on
otherwise reusable descriptor payloads. That is a potentially severe
frame-pacing regression, and a pre-drain changes ring generation, which
can itself prevent descriptor reuse.

A safe redesign would need to decide whether a new allocation is required
without violating guest-memory/descriptor-lock ownership, or provide a
retry mechanism that releases the cache mutexes, drains the exact GPU
fence and then **revalidates** every guest descriptor binding before
committing the draw. Both require a separate integration review.

## Scope and limits

This commit adds a host-only executable regression and CI hook. It does
not change Vulkan runtime, scheduling, descriptor layout, cache locking,
render order, or artifact packaging. Descriptor-buffer availability on
the actual console depends on the runtime device's advertised extension
and features. The witness does not prove that a particular game ever
took this path, and does not resolve FPS stalls, freezes or missing HUD.
