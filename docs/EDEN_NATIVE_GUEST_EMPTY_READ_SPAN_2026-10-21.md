# Eden Encore — reset an empty guest read's stale span

The maintained native core/video_core `GuestMemory::Read(u64,size_t)` can be called again on the same object. The old zero-length return set `m_is_data_copy` and returned `{}` but retained the `m_data_span` pointer and `m_span_valid` flag from the prior nonempty direct alias or copied fallback. Callers inspecting `data()` after an empty request could observe a stale host address.

The new zero-length branch clears the span and its validity flag before returning. The write-scoped destructor already returns immediately when `size()==0`; it is unchanged. Nonempty direct mapped spans, copied fallback, CPU/GPU cache flush, writeback and invalidation behavior are unchanged.

`tools/check-native-guest-memory-empty-read-host.py` builds the **actual selected maintained header** with a tiny fake native memory implementation under C++20 ASan/UBSan. It exercises a zero-read after a direct alias, zero-read after copied scratch data, reuse with a later nonempty request and no empty-scope writeback. Preflight and fast gate run the witness. This is correctness protection, not demonstrated GPU/frame-time improvement.

**425/491 files accounted for, 4 engine sources remain, 62 launcher UI sources separate.**
