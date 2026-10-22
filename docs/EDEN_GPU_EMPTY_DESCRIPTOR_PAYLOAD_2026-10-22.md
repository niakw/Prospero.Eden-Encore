# GPU descriptor payload: empty layouts (22 October 2026)

## Scope
The active Vulkan graphics pipeline keeps an immutable `num_descriptor_entries`
count per shader pipeline. For zero-entry layouts, the descriptor queue uses
`AcquireKnownEmpty`, but the later draw configuration still evaluated a
zero-byte `memcmp` and constructed empty iterator ranges from
`entries + num_descriptor_entries`. The cached vector can be empty, making
its `data()` pointer null. Neither operation is necessary in that case.

## Change
- Only run byte-wise equality/inequality comparisons for nonempty layouts.
- Clear the cached vector instead of forming the pointer range for empty layouts.
- Retain the first-use ring allocation, frame ownership, stage descriptor
  refresh, draw submission and all nonempty descriptor comparisons.
- Keep the pinned Vulkan reconstruction generator and active graphics TU in parity.

## Verification boundary
- `tools/check-ps5-known-empty-graphics-descriptors-host.py` exercises
  source-extracted comparison and snapshot code in C++ at -O0/-O2 with UBSan.
- It tests empty cached payloads and null pointers, first-use ring generation,
  pipeline rebind, one-entry unchanged and changed descriptor data.
- The fast host gate also checks the exact regenerated active Vulkan sources.
- No console graphics performance, HUD pixels or frame pacing is inferred from
  these host checks. No JIT profile flag is toggled.

## Recheck
Native compile and complete preflight must pass for this exact code, followed by
target hardware qualification only when there is a performance/correctness
reason to run a new title test.

## Compute path follow-up

The compute pipeline had the same legacy 1024-entry guest descriptor fallback
in `Acquire(0)`, and `RasterizerVulkan::DispatchCompute` ran the queue
preflight before reading its active immutable shader descriptor count.
For a descriptor-free compute shader this could block the GPU worker for
payload space it would never consume, including while preparing a dispatch.

- Native `ComputePipeline::HasDescriptorEntries()` reports the immutable
  `num_descriptor_entries` count.
- The compute owner selects the pipeline before deciding whether a guest-queue
  preflight is necessary; on a real wait it flushes guest invalidations and
  selects the current pipeline again.
- `ComputePipeline::Configure` selects `AcquireKnownEmpty` only for exact
  zero-entry layouts. Nonempty shader payloads continue the ordinary path.
- Descriptor-buffer ring allocation, compute bindings and barriers are
  unchanged, even for zero-entry shaders.
- `tools/check-ps5-compute-empty-descriptors-host.py` checks source-selected
  behavior under native defines, both C++ optimization levels and UBSan.
- The Vulkan source generator reproduces the new compute header, pipeline
  and rasterizer changes; the core fast gate passed.

This qualifies a host-side contention elimination, not PS5 frame pacing.
The archival register still lists zero unreviewed emulator source files.
