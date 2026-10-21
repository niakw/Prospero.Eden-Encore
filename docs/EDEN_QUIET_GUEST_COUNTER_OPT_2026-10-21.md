# Eden Encore — no atomic diagnostic counters in quiet gameplay

**21 October 2026.** `headless/performance.h` previously counted every guest idle/wake and graphics conditional-rendering decision in shared atomics, even when detailed profiling was disabled. These data feed diagnostic reports only and are not part of guest scheduling or rasterizer decisions.

Both `CountIdle` and `CountCondition` now check `detailed_gpu_profile` first and skip all relaxed atomic RMW operations when false. When detailed profiling is ON, the original counters, per-core data, and index bounds are preserved. Reporting values stay zero in quiet gameplay by design; no lock, guest sleep/wake, graphics predicate, or timer logic is changed.

The source-extracted host witness `tools/check-native-quiet-counters-host.py` builds the actual two inline functions under Clang ASan/UBSan, exercises 100,000 quiet calls with no counter changes, then validates diagnostic collection and OFF/ON transition. The source preflight runs the witness.

**Coverage:** 418/491 sources handled; **11 engine sources** still need optimization review; 62 launcher interface sources tracked separately. No PS5 FPS or stability claims until the final console test.
