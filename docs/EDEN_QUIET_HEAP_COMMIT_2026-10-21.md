# Eden Encore — heap growth without synchronous diagnostics in release

On the PS5 native direct-memory path, `src/memory_pages.cpp::CommitMemoryRange` used four monotonic timestamp queries, `snprintf`, and a kernel log message for every successful heap growth. A synchronous expansion may occur during startup, transitions, or asset loads. It should not also do diagnostic syscalls in a final release whose detailed logging is off.

The real function now wraps only those clocks and the post-zero report in `EDEN_HEAP_GROWTH_TRACE`. This definition is added **only** to the `common` target in the `EDEN_DEV_PROFILE` configuration. Release keeps all allocations, fixed mappings, zeroing, fail-closed ownership and physical return values exactly as before. Other startup/exception logging and table mapping behavior remain unchanged.

Test: `tools/check-native-quiet-heap-commit-host.py` extracts the maintained function; builds PS5_NATIVE with stubbed SDK calls under ASan/UBSan twice, asserting that release uses no timer/log and dev makes four timer calls/one report while both map and clear memory identically. Device timing remains unmeasured.

**Coverage 419/491, engine backlog 10, launcher 62 separated.**
