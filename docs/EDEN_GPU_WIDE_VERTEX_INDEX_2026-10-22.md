# Native GPU geometry buffer bounds — 22 October 2026

## Corrected source paths

The selected, maintained guest BufferCache contained two independent
32-bit truncations while calculating GPU-virtual geometry buffer lengths:

- `UpdateVertexBuffer` cast `limit.Address()+1 - array.Address()` to
  `u32` before evaluating the extent. A valid 4 GiB range could become
  zero, suppressing the vertex binding entirely; a slightly longer
  range could become an incorrectly tiny vertex buffer.
- `UpdateIndexBuffer` independently cast the GPU range to `u32`, and
  calculated `(count + first) * FormatSizeInBytes()` in 32-bit
  arithmetic. Either overflow could cause an indexed draw to miss
  required geometry data.

Both methods now check the exclusive GPU range endpoints in `u64`,
calculate all relevant byte counts in `u64`, and clamp the result to
the `u32` interface consumed by `FindBuffer`. The vertex path still
uses the existing `MaxContinuousRange` clip for large or invalid-end
ranges and additionally retires a vertex binding if that clip returns
zero bytes.

No code changes were made to the pinned shipping backport, source shader
compiler, texture cache, guest scheduler or draw descriptor queue.
Two independent native-source replay checks reconstruct the extra
geometry bounds guards after the earlier buffer-cache transformations.

## Targeted host regression

`tools/check-native-wide-vertex-buffer-range-host.py` compiles the
real `UpdateVertexBuffer` method with UBSan at `-O0` and `-O2`.
The fixture tests an ordinary binding, exact and larger-than-4-GiB
address ranges, inverted addresses, an empty contiguous mapping,
an unmapped CPU translation, and a clean dirty flag.

`tools/check-native-wide-index-buffer-range-host.py` compiles the
real `UpdateIndexBuffer` method with UBSan at `-O0` and `-O2`.
Its draws independently set their dirty flags and exercise normal
indices, exactly-4-GiB GPU addresses, overflowed count-plus-first,
inverted and unmapped ranges, and the inline-index route.

The complete fast gate succeeded for both methods in both host
optimization modes. Full native PS5 build, exhaustive source preflight,
and security analysis are separately qualified.

## What is and is not established

These changes correct objective geometry range truncations and can
prevent a drawable vertex or index binding being accidentally dropped.
The historical game reports include missing textures and geometry
artifacts, but no telemetry establishes that one of these overflow
conditions occurred in those frames. No reduction in guest-frame
stutter or improvement in HUD/image correctness is claimed without
hardware evidence. Keep the PS5 console test deferred until the
remaining HLE/JIT/cache invalidation issues are independently qualified.
