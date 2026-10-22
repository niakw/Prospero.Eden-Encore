# Native JIT empty invalidation — 22 October 2026

## Problem

The native Dynarmic `EmitX64::InvalidateBasicBlocks` previously entered
`BlockOfCode::EnableWriting` and `DisableWriting` even when the selected
guest-code invalidation matched no compiled block. On PS5 native code areas,
changing an existing RX page to RW and back can entail costly protection
transitions. Empty invalidations require no instruction patches.

## Change

The native-only emitter now exits before changing code-write permissions
when `locations.empty()`. A nonempty set always follows the existing
`Unpatch` / descriptor-removal / RX-publication sequence. No JIT policy
switch, guest instruction translation, code sharing, compiler scheduling,
A32/A64 configuration or shader invalidation was changed.

The shipping source was kept as a minimal, exact derivation of the pinned
common emitter source. The host emitter is intentionally unchanged.

## Regression witness

`tools/check-native-jit-empty-block-invalidation-host.py` extracts the actual
maintained native C++ method body, compiles it at `-O0` and `-O2` with
UBSan, and verifies both the empty and populated invalidation paths.
`tools/check-maintained-common-emit-x64.py` reconstructs both native/host
variants, including source selection in the two CMake profiles.

The fast gate succeeded, including the C++ regression and reconstruction.
Full preflight, CodeQL and PS5 native build are separate qualifications.

## FC27 evidence and limitation

In archived detailed telemetry from 21 October 2026, some early five-second
windows show ~4.2 s of cumulative JIT compiling on three emulated guest
cores. Later five-second windows show almost no JIT activity yet many
thousands of contended cache accesses (e.g. 16,029 buffer lock contentions
and ~148 ms aggregate buffer lock waiting in one window). Therefore one
native-JIT fix cannot account for all gameplay stutter.

This prevents a demonstrable pointless JIT permission change. The frequency
of no-op invalidations and improvement on target hardware are not established
by host tests. Avoid console retests until a meaningful release candidate
covers the remaining cache/HUD and pacing hypotheses.
