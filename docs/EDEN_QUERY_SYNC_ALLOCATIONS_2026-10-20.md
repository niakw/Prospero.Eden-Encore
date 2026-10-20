# Query sync: reserve destination handles before the buffer-cache lock

## Hypothesis and falsifiable check

`QueryCacheRuntime::SyncValues` appends one destination handle per grouped
guest-memory range while holding the buffer-cache mutex. The vector is moved
into the recorded command at the end of every call, so its next use can grow
from zero capacity again. Geometric growth reallocates and copies earlier
handles while other CPU/GPU work may need the same cache lock.

The group count is already known before taking the lock. Reserve exactly that
count there, retaining the existing buffer acquisition, synchronization mode,
range order and recorded-command ownership. This should reduce destination
vector allocation to one per nonempty batch, with none under the mutex.

A source-extracted host check must compare the pinned and maintained buffer
acquisition code for empty, small and large batches and repeated moved-out
vectors. It must count allocations and verify identical acquisition arguments,
handles, offsets and locking. Generator replay must match the maintained unit.
Existing page-span and conditional-render tests remain required.

This changes host allocation work, not GPU fence or guest-wait semantics. Host
allocation counts do not establish PS5 frametime or freeze improvements.

## Second hypothesis: quadratic range grouping

For N results on separated pages, the existing grouping loop scans all earlier
groups: N(N-1)/2 comparisons, or 523,776 for 1,024 results. A result spanning
two pages can also connect two existing groups, leaving overlapping destination
ranges because the loop stops at its first match.

Build a reusable array of query indices, sort it by guest address, then merge
adjacent/overlapping page spans in one pass. Redirect each original query to
its merged group; the later copy-building loops still traverse queries in their
original order. No fence or synchronization operation is removed. The check
must compare covered spans, original-query redirects and copy coverage against
an independent oracle over sorted, reverse, shuffled and page-crossing batches.
Count comparator calls instead of claiming a noisy timing or PS5 FPS result.
The previous grouping code is retained as an explicit negative/performance
fixture in `tools/fixtures/query-sync-linear-grouping.inc`.

## Measured host work in the stabilized batch

The source-extracted fixture reports 1,023 page comparisons for 1,024
monotonic pages, versus 523,776 probes in the old loop. `is_sorted` avoids
sorting monotonic pages and arbitrary addresses within a single page; shuffled
pages use the sort-and-merge path. Thirty-two seeded shuffled batches, reverse
order, empty input, page-local queries and a crossing-page bridge preserve
exact page coverage and original-query redirects under ASan/UBSan.
The separately compiled buffer-acquisition block reports zero destination
allocations under its mutex, versus eleven, and identical acquisition calls
and output handles/offsets. Strict whole-unit generator replay also passes.

The sorting path adds one reusable `size_t` index per slot of retained scratch
capacity (8 KiB for 1,024 slots on the 64-bit target). This is an explicit memory
tradeoff for removing repeated scans; the vector belongs to the query runtime
and is destroyed with it. Small batches and native frametime impact still need
measurement on the final console build.
