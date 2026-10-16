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

## Native capability and release build gate

The release recipe in `tools/build-package.sh` selects
`EDEN_PS5_VULKAN=ON EDEN_VULKAN_DRIVER=RADV`. The active vendored RADV source
(`vendor/encore-active/ps5-mesa/src/amd/vulkan/radv_physical_device.c`)
advertises `EXT_descriptor_buffer = true` and `descriptorBuffer = true`.
The native application's `headless/dev_vulkan.h` defaults
`disable_descriptor_buffer` to `false`, including the title reset.
The Vulkan device adapter retains the feature when supported by the
selected physical device, and ring initialization also requires buffer
device address support and usable host-visible/coherent memory.

The host witness now pins this production source path. Thus the unsafe
fallback is *source-reachable* on the configured driver, not merely a
desktop-only code path. It is **not** proof that the feature was enabled
on a particular boot or that a game's descriptors exhausted the ring.
Runtime extension negotiation, ring allocation and per-game use remain
unmeasured. No new console execution is requested.

## Engineering trade-off

The host fixture now proves the *two-outcome, same-observation* case with
production source-extracted `PreflightCapacity` and `Allocate`:

1. An exhausted ring, matching generation and matching entry count,
   with a byte-identical guest payload: `ConfigureDraw` reuses the old
   allocation and requires **no GPU wait**.
2. Exactly the same pre-lock ring and pipeline metadata, but one changed
   guest descriptor: `ConfigureDraw` allocates and can reach
   `scheduler.Finish()` **under the cache locks**.

Passing the full layout to preflight to cover the second case necessarily
causes an unnecessary `Finish` in the first case; it also changes the ring
generation and invalidates the previously reusable allocation. Therefore,
changing a getter or making `PreflightCapacity` unconditional does **not**
provide a no-regression fix.

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

## Future redesign acceptance conditions

A real fix must preserve all three properties in the same draw:
- Cache-dependent descriptor identities and buffer/image lifetimes remain
  valid from descriptor collection through the GPU command submission.
- An identical payload still reuses its previous allocation without an
  unnecessary GPU drain or extra descriptor allocation.
- A changed payload can reclaim full-ring capacity without holding the
  guest texture/buffer mutex pair during `scheduler.Finish()` and without
  dropping or duplicating commands, draws, upload barriers or query updates.

A two-phase staging/retry mechanism would also need to detect invalidations
between lock release and reacquisition and restart descriptor capture safely.
`ConfigureImpl` already updates buffer bindings, texture views, render
targets and scheduler work **before** reaching `ConfigureDraw`: simply
re-running it is not a proven idempotent retry. Snapshotting raw cache-owned
image-view pointers without lifetime pinning is likewise unsafe.

The current contract test is deliberately a *negative* safety gate, not an
emulator performance improvement. No console test is required to establish
these source-level trade-offs, but host tests cannot establish FC27 behavior.

## Scope and limits

This commit adds a host-only executable regression and CI hook. It does
not change Vulkan runtime, scheduling, descriptor layout, cache locking,
render order, or artifact packaging. Descriptor-buffer availability on
the actual console depends on the runtime device's advertised extension
and features. The witness does not prove that a particular game ever
took this path, and does not resolve FPS stalls, freezes or missing HUD.
