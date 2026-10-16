# Guest memory span page boundaries — 16 October 2026

The pinned memory source compared the block containing the first byte to
the block containing `addr+size`. For a half-open range ending exactly
at a page boundary, that indexes a page outside the requested range,
leading to unnecessary null fast paths and potentially a one-past-end
page-table access at the virtual address-space limit.

The maintained core memory source differs from the pinned memory.cpp
only in its two GetSpan overloads. They reject zero-size, overflowing
and out-of-range requests and compare against the last included byte
`addr+size-1`. Both the optional A32 arena derivative and the native
memory diagnostic derivative build from this versioned source. No
JIT mapping, GPU cache, or guest memory permission policy changes.

The Clang ASan/UBSan fixture compiles the extracted pinned and active
GetSpan methods. It reproduces the old boundary false negative and
tests valid last-page spans, unmapped crossings, zero-size, and overflow.

This proves a source-level page-range correctness fix only, not any
FC27 FPS, HUD or freeze improvement. No console package or test.
