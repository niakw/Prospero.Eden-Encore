# Eden Encore — Standard A64 JIT compilation phase witness

Branch: dev/ps5-sparse-jit. Host-only implementation and regression.

## Evidence

Historical FC27 telemetry showed long presentation intervals correlated with
A64 compilation bursts, without identifying what fraction of the compiler
cost came from translation, optimization or native emission. The previous
DEV hook `eden_jit_phases` ran only for experimental bounded batch/shared
modes, not the normal per-core, non-batch Dynarmic compiler. Consequently,
`jit_dups=on` could not count repeat compilation in the standard path.

## Change

The complete active `a64_interface_standard.cpp` now samples clocks
around `Translate`, `Optimize` and `Emit` in its default non-batch
branch **only** when compiled with `EDEN_JIT_A64_DEV_PROFILE` and
detailed logging is enabled. It uses the already-declared weak
`eden_jit_phases` callback and passes the actual location descriptor.
With `jit_dups=off` phase totals can still be observed; duplicate
map recording requires the existing explicit opt-in and its associated
memory/lock overhead. No clock reads or callbacks are introduced in
release and quiet-DEV execution, and no changes affect guest code,
cache invalidation, JIT allocation, scheduling or GPUs.

The host fixture compiles the extracted real default non-batch code
in release and DEV configurations under ASan/UBSan and verifies
both silent runs and one detailed compile report. All other CMake
selection modes and the shared/batch behavior remain unchanged.

## Limits

These are **aggregated per-core compile phases**, not a one-to-one
guest-frame critical path. Historical 15 October logs predate this
hook. The user still needs an identified native PS5 diagnostic build
and same-scene frametime/guest-progress evidence before claiming that
repeat compiles cause a freeze or that FPS improved. Do not activate
shared or batch JIT just to collect diagnostics.
