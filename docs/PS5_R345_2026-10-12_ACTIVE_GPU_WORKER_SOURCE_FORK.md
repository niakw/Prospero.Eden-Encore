# R345 — Native PS5 GPU worker code no longer rewritten by CMake

Branch `dev/ps5-sparse-jit`. The original pinned Eden headers and `.cpp` remain immutable in `vendor/sources/eden`. Our complete modified GPU source now lives in `vendor/encore-active/eden-gpu` with **both** dev/quiet variants:

- `gpu_thread_quiet.cpp`: no `EDEN_DEV_PROFILE` timers, retains 32-command PS5 queue and native pthread/stop-aware producer wake.
- `gpu_thread_dev.cpp`: identical command/fence semantics but includes opt-in detailed GPU profiler instrumentation.
- `include/video_core/gpu_thread.h`: native thread lifecycle and exact 32-slot queue type.
- `include/common/bounded_threadsafe_queue.h`: stop-aware producer wait using the consumer condition variable.

In native PS5 CMake, these tracked files are copied directly with `configure_file(... COPYONLY)` into the mutable build tree. The historical CMake source transformations remain only for non-PS5/legacy source compatibility in the `else()` branch. The native path does **not** run the old `string(REPLACE)` transformations.

## Source and execution-equivalence evidence

`tools/check-vendored-gpu-thread.py` extracts the **exact old production CMake source-derivation block** from `headless/CMakeLists.txt`, runs it using CMake itself against the pinned Eden original in both `EDEN_DEV_PROFILE=ON` and `OFF`, and compares full emitted sources to the versioned fork. Only machine-specific header prefixes from the original CMake emitter are removed (the production CMake target already includes `headless/`). It also runs the **new actual PS5 CMake branch**, checks each copied header and worker variant, and validates queue size and selective profiling. All four files pass local exact equivalence.

R344 corrected a separate portability defect in Vulkan shader source: the old generator emitted an absolute Mac include path. The original `tools/check-vulkan-shader-workers.py` asserted that obsolete path and failed the R344 source CI; R345 updates the assertion to the portable include without weakening worker topology assertions.

This isolates the GPU command producer and worker from build-time string rewriting. Other CPU/JIT/HLE, OpenGL and guest GPU core transforms within `headless/CMakeLists.txt` remain unmigrated, and no new console performance test has been requested. Exact equivalence to existing binaries is a source-build property, not proof that FC27 menu freezes or gameplay stutters are fixed.
