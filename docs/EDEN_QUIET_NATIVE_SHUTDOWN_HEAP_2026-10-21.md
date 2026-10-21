# Eden Encore — silent native shutdown without heap ownership scans

Native `headless/main.cpp` shutdown always drains the **current thread's freed allocation cache** via `eden_heap_release_current_tcache()`. This cleanup remains unconditional, including when returning directly to the launcher. The old path then synchronously walked the allocator's ownership roots and printed a second native heap snapshot, even in release mode with Detailed Logging OFF.

The production path now gates **only** `eden_heap_report_roots("core_destroyed")`, `ps5_opengl_heap_snapshot("post_cache_drain", 0)`, and their associated print behind `detailed_gpu_profile`. They are non-destructive observations; no live heap mapping is freed, no guest threads run under these reports, and the core stop/JIT finalization ordering is unchanged.

Source-extracted host proof `tools/check-native-quiet-shutdown-heap-host.py` compiles the exact maintained block under ASan/UBSan and verifies TLS drain in every mode and snapshots only in detailed mode. Fast gate and preflight both run it.

**Coverage 423/491; 6 engine/runtime paths still pending, 62 UI launcher files separate.** Console responsiveness after shutdown has not been measured.
