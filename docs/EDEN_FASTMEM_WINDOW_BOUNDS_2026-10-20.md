# A32 fastmem window: overflowing page-range clipping

The broader inventory found `src/host_memory.cpp` outside the 478-row contract
graph, although CMake compiles it into `common` and existing bridge checks read
it. The graph must not be described as a complete inventory of Encore code.

Hypothesis: `Window::Pages` clips the end using `min(offset + length,
WindowBytes)`. The addition can wrap before clipping. At offset 1 and length
`SIZE_MAX`, the derived last page becomes far larger than the A32 window.
`Unmap` then iterates over page arrays using that last page; `Protect` derives
an invalid iterator. Public unmap/protect calls do not independently bound it.

Preserve the helper's existing clipping semantics by limiting the length to
`WindowBytes - offset` before addition. A source-extracted ASan/UBSan witness
must reject the original result and verify zero, invalid, ordinary, cross-page,
end-of-window and maximal-length inputs. No whole guest-address-space walk or
console run is needed to reproduce the range error.

This is a bounds correction for the optional A32 fastmem window. It does not
enable that window, alter the A64 JIT, or establish a cause of FC27 freezes.

## Refresh work hypothesis

Under the window mutex, `Refresh` evaluates `Own(page)` and `Own(page+1)`
for every map byte, repeating the same page-access lookup on consecutive
iterations. The access/alias arrays are stable during this loop and distinct
from the map being written. Carry the successor value into the next iteration.
Compare the entire output map against the previous loop across page/alias
boundaries and the final guard page, while counting helper evaluations. N map
bytes should require N+1 evaluations instead of 2N. This is a source-work
measurement, not a PS5 frame-time benchmark.
