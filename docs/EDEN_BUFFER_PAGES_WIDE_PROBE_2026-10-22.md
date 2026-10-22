# CPU writes: two-word guest buffer ownership probe (22 October 2026)

## Identified inefficiency
`Eden::BufferPages::NeverRegistered` maintains a 16-GiB guest physical
registration bitmap with 4-KiB granularity. Its previous 64-KiB size
threshold caused every larger write/unmap/readback to fall through to
locking even when all the bitmap pages were definitely never owned by
a GPU buffer. Normal operation still requires conservative locking for
any previously registered page, unknown coverage, invalid spans or
queries beyond the bounded probe.

An arbitrary unaligned **256-KiB** range covers at most 65 guest pages,
intersecting at most **two** 64-bit bitmap words. The same two atomic
loads therefore safely inspect four times the old byte range. The
change does not relax the safety requirements or change registration,
cache invalidation ordering, dirty-state publication or shader/texture
invalidation.

## Qualified source and tests
- `headless/buffer_pages.h`: raise only the read-side bounded probe from
  64 KiB to 256 KiB, retaining the immutable ownership witness and
  fail-closed overflow/unknown branches.
- `tools/check-native-buffer-pages-wide-probe-host.py`: actual header
  under UBSan in `-O0`/`-O2`, across an unaligned two-word boundary,
  first/last owned pages, adjacent distinct pages, overflow and >256-KiB
  fail-closed behavior.
- `tools/check-native-batched-buffer-invalidation-host.py`: never-owned
  128-KiB batch skips the buffer lock but still invalidates shader/query;
  >256-KiB batch retains original cache invalidation.
- `tools/check-native-single-range-buffer-invalidation-host.py`:
  equivalent per-range ordering and fallback.
- `tools/check-ps5-never-owned-buffer-unmap-host.py`:
  independent unmap and query/shader invariants.
- `tools/check-ps5-buffer-readback-elision-host.py`: source-selected
  ASan/UBSan readback witness, now also part of the fast gate.
- Fast gate on this branch succeeded after test qualification;
  full preflight and native build are independently checked.

## Scope and performance limits
In 21 October FC27 diagnostics, a late five-second window had about
16,029 recorded buffer-lock contentions and 147.9 ms total waiting,
but no individual tracked lock wait exceeded 1 ms. Draw-pipeline
configuration and GPU command recording dominate other sampled costs.
Those measurements were collected with advanced diagnostics enabled,
which changes lock instrumentation. They do not prove the frequency
of CPU write operations between 64 and 256 KiB on quiet firmware.

Thus, this patch removes a provable unnecessary lock acquisition for
unowned spans in that range. **No measured gain in game fluidity or
HUD/texture correctness is claimed.** Keep the JIT shared/compile-ahead
experimental paths separate until quiescence and stale-code controls
are validated.
