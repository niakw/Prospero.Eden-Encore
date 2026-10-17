# GPU granular range native memory manager fix — 2026-10-17

The pinned MemoryManager::IsGranularRange() computes the continuous big-page
limit using `page_index & big_page_mask` where page_index is a number of
64-KiB big pages. The limit must instead use the **byte offset inside the
big page**: `gpu_addr & big_page_mask`.

For a mapped continuous 64-KiB page, query address 0x1fff0 with size 32:
the original code returns true despite crossing the big-page boundary. The
native-only derived file now rejects this. Two 4-KiB fallback checks are
written as subtract-before-compare, preventing size additions from wrapping.
A guard also rejects zero-length, out-of-address-space and overflowing
queries before calling GetEntry (which indexes the page vectors).

The regression executes the original C++ method and the real CMake-produced
native method with synthetic mapped-page states and boundary inputs. It
demonstrates that valid same-page accesses stay valid and crossing/invalid
ones are refused. Neither the vendored source nor external APIs are changed.
This establishes a correctness fix, **not a proven FC27 stall fix**; it does
not alter active GPU synchronization, shader compilation, or deferred bridge
#187. No console title test or release was requested.
