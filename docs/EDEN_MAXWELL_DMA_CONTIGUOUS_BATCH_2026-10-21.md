# DMA pitch-copy coalescing (Maxwell U81)

The active `MaxwellDMA::Launch` performed a `MemoryManager::CopyBlock` and destination flush per row, even when the source and destination buffers represented two distinct, contiguous linear spans.

An entirely statically qualified fast path now uses one `CopyBlock` when source and destination pitches exactly equal row width, rows and width are nonzero, `width*rows` fits the u32 buffer address span, both u64 end addresses are representable, and the two spans **do not overlap**. Any other transfer falls back to the exact original per-line loop. The DMA semaphore release and `FlushCaching` remain unchanged.

The strict pinned-source oracle `tools/check-native-dma-extent-host.py` admits only this transformation atop already qualified pitch/extent guards. New source-extracted C++20/ASan/UBSan `tools/check-native-dma-contiguous-host.py` exercises valid contiguous and adjacent regions, overlapping and self-copies, signed pitch mismatches, empty transfers, u32 extent overflow, and GPU address overflow.

**Source coverage 417/491; 12 engine files outstanding; launcher 62 excluded.** A reduced per-line dispatch cost is expected only on qualified contiguous DMA workloads. No PS5 FPS or freeze claim.
