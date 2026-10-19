# Eden Encore — JIT invalidation extents (2026-10-19)

Branch: dev/ps5-sparse-jit. Native selected source owners: complete maintained A32 interface and normal A64 interface; opt-in shared A64 is kept structurally identical.

## Defect

A32 and A64 previously constructed closed Dynarmic invalidation intervals as `start + length - 1`, before testing for a zero length or address wrap. A zero-length request could produce an unrelated range; a nonzero overflow could yield a reversed interval and leave stale translated code in the JIT. The defect is independent of graphics frame-rate settings.

## Conservative correction

- `length == 0`: no mutex acquisition, halt or invalidation.
- Representable nonempty address range: unchanged closed-interval invalidation and JIT halt.
- Range extending past its address width: request full code-cache invalidation and halt instead of publishing a wrapped/inverted interval.
- Applies to maintained A32, regular A64 and the disabled shared A64 variant. The original pinned vendored sources are untouched.
- Source-selection/parity scripts and sanitized source-extracted host regression cover both edge types. The original unpatched bodies must fail the same behavioral tests.

No A64 per-core cache enlargement, fastmem policy change, shared JIT activation or frame pacing change. This prevents a demonstrable invalidation hazard; it does **not** establish that FC27 stalls or freezes were caused by this flaw. Native PS5 build and matched-console frametime/guest-progress comparison remain required.

## Skip redundant range bookkeeping during a pending full-cache clear (2026-10-20)

All three native maintained JIT paths (A32, normal A64 and opt-in shared A64) now
skip Boost interval-set insertion when `invalidate_entire_cache` is already true
under the existing mutex. A full clear supersedes narrower invalidations and
consumes the same pending halt; no lock, halt, global cache clear or entry
acknowledgment is removed. The source-extracted ASan/UBSan regression now
checks initial full clear, an overflowing request and subsequent repeated
range invalidation, including that earlier ranges remain intact until the
full clear consumes them. Host-only structural work elimination, not a
measured console frametime improvement.
