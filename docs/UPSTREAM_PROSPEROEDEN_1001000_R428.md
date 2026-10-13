# R428 — selective upstream ProsperoEden v1.001.000 (d7f2764)

Upstream commit: https://github.com/blackbearreloaded/ProsperoEden/commit/d7f2764f8ecf8bdbd979eece2b402621edceee2f (2026-10-13, 115 files changed).

## Integrated without modifying pinned source archives

1. **Boost ADL small-vector:** Eden's pinned `src/video_core/texture_cache/util.h` tests `BOOST_VERSION` without including `boost/version.hpp`. In some translation units the macro is undefined, selecting a heap-backed `std::vector` instead of `boost::container::small_vector` even with modern Boost. Generate a private `video_core` include override containing the missing include. No change to the upstream tarball. Upstream measured ~2,300 unnecessary allocations out of ~3,400 per frame in one game; **not measured on Encore yet**.
2. **ASTC array recompression:** Eden currently decodes every array layer in a mip level into one RGBA scratch buffer before BC1/BC3 recompression. Upstream demonstrated a case with 121 layers requiring ~484 MiB temporary CPU memory; split the same operation into layer-sized pieces. Preserve per-layer BC compressed output order and offsets and existing quality choice, without changing when textures are converted or switching compression modes.
3. **Logging write bursts:** The pinned Eden error backend flushes after every error (and with an explicit `Flush` or per-line logging). On PS5 a stream of guest invalid-memory reports can stall guest CPU cores due to synchronous storage IO. Generate a private `common/logging.cpp` overlay, preserving all emitted entries and explicit flush; during an error burst, flush no more often than every 100 ms unless the log limit is exceeded. **Tradeoff:** after an abrupt process termination, up to 100 ms of recent error lines may remain in the OS/file buffer. This path must be monitored in crash diagnostics.

All modifications use CMake configure-time substitutions with fail-closed pinned-source anchors. The existing source archive checks, PS5 native pipeline, launcher, profiles and per-game control mapping stay unchanged. `tools/check-upstream-texture-memory-r428.py` compiles a Boost/C++ host fixture and checks ASTC layout and the log-throttle boundary.

## Findings *not* automatically enabled

- **CPU physical core discovery by pair timing**: upstream `AdjacentCpusShareCore` is new evidence on firmware with invalid SMT CPUID. Our FW 13.60 code requires verified CPU masks; a timing-only SMT result could be affected by scheduling, frequency variation and sibling contention. Port as diagnostic before using it for affinity.
- **Guest clock adaptive slowdown (up to 15%)**: changes guest-perceived time and may reduce self-imposed 30→20 FPS switches without improving actual rendering throughput. It risks affecting game timers and determinism; requires explicit per-game A/B and must not be conflated with fewer stutters.
- **ASTC CPU asynchronous policy**: can avoid 130–290 ms first-use decode hitches but can temporarily display a missing/low-detail texture, hurting HUD/pitch fidelity. Keep existing Encore policy until qualified on FC27 and BOTW with warm/cold cache runs.
- **Yield-to-guests cache-lock arbitration**: upstream sleeps/spins up to 2 ms to hand off texture/buffer cache locks. Our guest/GPU mutex instrumentation differs and defaults to an upstream blocking path when detailed profiling is off. Merge only after deadlock and critical-section order review.
- **PS5 OpenGL SDK 1.0.2, theme Canopy, new launcher UI, runtime memory ABI**: different dependency and UI contracts; not suitable for a mechanical merge with Encore's already customized native renderer and neon-tropical interface.

## Validation gates

Core source regressions including R428 host fixture; all pinned dependency source digests unchanged; PS5 build required for actual CMake generation and linkage; only then a combined FC27/BOTW test. Neither the upstream FPS claims nor its memory measurements are presented as measured Encore results.
