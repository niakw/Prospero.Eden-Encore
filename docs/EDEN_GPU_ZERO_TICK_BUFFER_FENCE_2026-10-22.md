# Guest buffer zero-write-tick fence elision

## Verified source invariant

The guest Vulkan BufferCache looks up resident GPU buffers in
`FindBuffer`. Under accurate-fence mode, a cache hit may call
`SynchronizeBufferWrites`. The base Buffer's `write_tick` initializes to
zero. The only GPU-write path sets that field to
`BufferCacheRuntime::CurrentTick()`. On the Vulkan scheduler,
`Wait(0)` does not perform a wait.

Before this patch, every such lookup with an untouched buffer probed
`runtime.IsFree(0)`, reading the scheduler's fence state even though no
write fence was associated with that buffer.

## Native-only change

`vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h`
now checks `buffer_tick != 0` before calling `runtime.IsFree`.
All nonzero, completed and pending write fences follow the original paths.
No GPU buffer mutation, guest write ordering, cache lock, shader invalidation,
texture invalidation, or descriptor scheduling was removed.

The shipping backport remains hash-pinned and unchanged. Two independent
source-reconstruction witnesses reproduce the native-only transformation:
`tools/check-ps5-buffer-pages-r437.py` and
`tools/check-vendor-consolidation-debt.py`.

`tools/check-native-zero-write-tick-fence-host.py` extracts the exact
maintained C++ method body and compiles it with UBSan at `-O0` and
`-O2`, verifying that:
- A zero tick causes neither a semaphore probe nor a wait.
- A nonzero completed tick still probes `IsFree`.
- A nonzero unfinished tick still calls `Wait`.
- A later zero tick remains independent of a previous wait.

The fast host gate succeeded. Source preflight, CodeQL, native PS5 build,
and gameplay performance are independent qualification stages.

## Performance / FC27 boundaries

This is a bounded reduction of unnecessary semaphore-state loads on
previously unmodified GPU buffers when the accurate-fence mode is in use.
Without a hardware counter for `getWriteTick() == 0` on actual FC27
draws, no throughput improvement is claimed. Previously captured FC27
stutters with stable 30 FPS, HUD inconsistencies and jersey texture defects
remain unresolved until an independently qualified render/guest-pacing fix
and eventual on-console verification.
