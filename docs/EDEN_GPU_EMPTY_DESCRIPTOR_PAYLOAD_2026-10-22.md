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
