# October 15 GPU cache/JIT upstream review — source qualification only

Scope: `dev/ps5-sparse-jit`; no new native build and no physical console test.

## Evidence from supplied Oct 15 FC27 traces

Two independent session files were analyzed separately. Their maximum *cumulative*
buffer-cache lock waits per ~5-second window were 176.2 ms and 252.2 ms.
For texture-cache mutexes the maxima were 120.9 ms and 510.1 ms.
These are sums across completed waits, not one stalled render frame and
not a causal proof of pause-menu freeze. Latest per-session results had
323 and 466 displayed frames >50ms, respectively. Do not merge session
counter resets or equate presenter FPS with guest simulation progress.

## Current upstream disposition

- ProsperoEden [#187](https://github.com/blackbearreloaded/ProsperoEden/commit/f1b83c21d157):
  high-priority, **not completely integrated**. This change includes much
  more than buffer lock elision: deferred guest writes, GPU-side replay before
  dependent commands, GPU-modified/fence exceptions, and core-scoped queues.
  Importing only the early deferred-write version would risk stale HUD/terrain
  textures. The `buffer_write_ahead.h` subcomponent is separately staged:
  it marks registered buffer pages only under an existing cache lock, stops
  at unregistered or GPU-owned pages, and is **OFF by default** (`cpu_write_ahead=0`).
  Offline sanitizer tests do not prove any speedup. The complete deferral
  semantics are not enabled or claimed.
- ProsperoEden [#188](https://github.com/blackbearreloaded/ProsperoEden/commit/b94216347b9a):
  **not integrated**. Direct JIT page table + page reuse need matching sparse
  commit order, page invalidation, new Dynarmic IR opcodes and host memory
  differential tests. Existing sparse JIT is not an equivalent implementation.
- ProsperoEden [#185](https://github.com/blackbearreloaded/ProsperoEden/commit/99e381ed29f7):
  **not integrated**. Dirty block-row texture refresh needs per-image, per-cache
  lifetime accounting and same-snapshot unswizzle verification; an earlier
  upstream variant left stale page state across title switches.
- ProsperoEden [#179](https://github.com/blackbearreloaded/ProsperoEden/commit/9c898feb254a):
  already covered by `headless/jit-compile-batch.inc` line 21.
- ProsperoEden [#183](https://github.com/blackbearreloaded/ProsperoEden/commit/a13e040cd502):
  equivalent 1.5ms guest VI composition delay already present.
- ProsperoEden [#181](https://github.com/blackbearreloaded/ProsperoEden/commit/6b4d27ff3352):
  256-entry native GPU queue already present.
- ProsperoEden [#178](https://github.com/blackbearreloaded/ProsperoEden/commit/96d8f4a8e852):
  native `video_core` ThinLTO + Zen2 already present.

## Stop conditions

No more user console trials for these source checks. Do not enable the
new write-ahead optimization on a release from host contracts alone.
Prioritize full write/read/fence ordering proof for #187, then independent
JIT memory differential verification for #188, then per-texture lifecycle
checks for #185. CI success proves source contracts, not FC27 gameplay.
