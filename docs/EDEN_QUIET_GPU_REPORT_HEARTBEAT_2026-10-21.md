# Eden Encore — keep freeze heartbeat, omit heavy quiet GPU snapshots

`headless/performance.cpp::ReportGpuThread` runs periodically in the native graphics reporting window. Previously it always called `ps5_opengl_heap_snapshot`, sampled direct memory and multiple GPU/HLE counters, wrote many diagnostic lines, and captured a CPU snapshot, even while Detailed Logging was OFF. Repeating such synchronous operations can consume time on the presentation owner thread.

The normal production path now **always publishes** `latest_gpu_report_frame` and `latest_gpu_report_ns` with the existing release/acquire synchronization, then returns immediately if `detailed_gpu_profile` is false. Thus the separate input-thread watchdog still detects long periods without GPU-owner progress and can emit its bounded stall report. Detailed Logging ON takes the original complete path unchanged.

Host proof: `tools/check-native-quiet-gpu-report-host.py` extracts the real maintained function's heartbeat and guard prefix, compiles with Clang C++20 ASan/UBSan, checks that quiet frames still publish heartbeat but never read diagnostic clocks, and that ON does. Preflight and fast gate run the witness. This reduces release-mode diagnostic overhead but does not prove an FPS or FC27 freeze improvement on console.

**421/491 source files handled; 8 engine-runtime files still pending, plus 62 launcher UI sources tracked separately.**
