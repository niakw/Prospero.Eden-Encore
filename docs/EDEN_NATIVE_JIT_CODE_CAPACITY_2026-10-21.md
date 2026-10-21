# Eden Encore — native JIT code allocation overflow guard

`BlockOfCode::AllocateFromCodeSpace` in the active native Dynarmic implementation previously compared `size_ + alloc_size >= maxSize_`. The input `alloc_size` can be large, and unsigned arithmetic can wrap before the comparison, letting an invalid request reach `EnsureMemoryCommitted`, `getCurr` and `memset`. This is a correctness boundary, not a proven in-game occurrence.

The guard now checks `size_ >= maxSize_ || alloc_size >= maxSize_ - size_` without adding. The same strict policy rejects exact-capacity allocations; permitted requests continue to commit, advance cursor and zero memory unchanged. No alternate JIT profile, sparse backend, signal handler or W^X permission transitions are altered.

`tools/check-native-jit-code-space-bounds-host.py` extracts the actual allocator method into a source-derived C++20 ASan/UBSan fixture and exercises normal, exact-fit and overflow requests, including `SIZE_MAX` corner cases. The checks run under the fast gate and complete preflight. **426/491 handled; 3 core engine sources outstanding; launcher UI 62 separately.** No PS5 FPS, JIT throughput or title stability result is inferred.
