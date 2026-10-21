# DMA buffer-copy span: prevent silent narrowing under GPU cache locks

The native renderer's `AccelerateDMA::BufferCopy` passes a 64-bit byte count
to `BufferCache::DMACopy`, whose `FindBuffer` and `SynchronizeBuffer`
operations narrow the amount to a 32-bit span. An amount greater than
`UINT32_MAX` could therefore synchronize only the truncated prefix while
the GPU copy and GPU-dirty bookkeeping retained the original large amount.
A zero-length copy could also reach registration checks unnecessarily.

Now `AccelerateDMA::BufferCopy` rejects zero or oversized amounts
**before** acquiring `buffer_cache.mutex`. `BufferCache::DMACopy` has
the same defensive guard **before** address translation and dirty-range
bookkeeping. Returning `false` preserves the established DMA software
fallback; valid byte counts are not changed. The DEV GPU bridge and pinned
Vulkan source generator match the native path byte-for-byte; the R437
maintained core-source reconstruction was extended with this transformation.

The source-extracted C++ fixture checks both actual entry guards at
-O0/-O2, and proves invalid spans perform no translation, lock or cache
DMA call, including zero, UINT32_MAX+1 and UINT64_MAX. Valid lengths
(1, UINT32_MAX) continue. It does not simulate a complete guest DMA copy.

This fixes a potential corruption/crash condition, not a measured cause
of FC27's 30 FPS stutter or missing HUD.
