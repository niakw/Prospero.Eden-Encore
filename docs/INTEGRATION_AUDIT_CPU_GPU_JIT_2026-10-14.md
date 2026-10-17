# Encore integration audit — CPU/HLE, GPU, JIT and memory

Date: **14 October 2026**. Single target branch: `dev/ps5-sparse-jit`.
This is a **source-path and build-selection audit** against concrete upstream sources.
It is not a statement that every upstream commit in every related repository
has been reviewed or that an improvement in FC27 gameplay has been measured.

## Critical distinction: runtime vs repository presence

A feature is not integrated merely because a file exists in
`vendor/sources` or `vendor/encore-active`. The build must select the source,
its relevant feature flag must be enabled, a native candidate must compile and
link, and gameplay behavior must then be verified on device. The inventory
of 22/22 dependencies in `UPSTREAM_GAP_REGISTER_2026-10-14.md` is **not**
a list of 22 complete functional upstream backports.

## Source and production status

| Priority | Feature and source | Encore status | Evidence and remaining verification |
|---|---|---|---|
| P0 CPU/HLE | Upstream scheduler + slab blocking mutex pairing | **Integrated, ON by CMake default** | `headless/CMakeLists.txt`: `EDEN_BLOCKING_GUEST_CONTEXT_LOCKS=ON`, core PUBLIC include and consumer override, scheduler source replaced by `vendor/encore-active/eden-threading`. `tools/check-upstream-guest-scheduler-locks.py` now checks a maintained cross-worker `std::binary_semaphore` context guard, rather than the upstream `std::mutex` (whose release from a different host thread is undefined); the unrelated slab mutex remains unchanged. This eliminates that **source-level ownership violation** but does **not** prove console compilation or fix FC27 gameplay. |
| P0 CPU/JIT | Ordinary per-core Dynarmic | **Compiled/active** | `tools/check-jit-stability.py` and `tools/build-package.sh` mandate ordinary Dynarmic in shipping builds. |
| P0 JIT | Cross-core shared A64 block cache, `JitGroup` | **Code exists but compiled OFF in shipping** | Encore CMake declares `EDEN_SHARED_JIT=OFF`, package build exports OFF, package asserts OFF. Main ProsperoEden sets `EDEN_SHARED_JIT ON` on native/Linux. This is a **deliberate stability divergence**; tests of these dormant classes do not establish production performance. |
| P0 JIT | Bounded successor compile batching | **Compiled OFF** | `EDEN_JIT_COMPILE_BATCH=OFF` in CMake and shipping package. |
| P0 JIT | Saved-block session precompile | **Unavailable in shipping configuration** | `headless/jit_list.h` has a structural no-op when shared JIT is absent; `headless/main.cpp` disables it. Prior instability means do not silently enable it. |
| P0 memory | Lazy guest memory commit from main ProsperoEden #156 | **Missing equivalent in current production memory path** | Upstream `src/host_memory.cpp` uses `AllocateGuestMemoryWhereUsed` and `CommitGuestMemory`, its `src/memory_pages.cpp` implements both; the corresponding Encore files do not contain these entry points. A separate sparse table/JIT experimental design in Encore is **not equivalent evidence**. |
| P0 memory | Progressive JIT code arena backing from #156 | **Different/incomplete mechanism** | Upstream uses `ReserveCodeRange`/`CommitCodeRange` in `src/memory_pages.cpp` and `headless/jit-allocator.h`; absent from Encore equivalents. Encore has separate experimental sparse JIT and allocation fallbacks and cannot simply cherry-pick. |
| P1 memory | Native package flexible memory request | **Integrated in packaging** | `tools/package-headless-native.sh` writes `kernel.flexibleMemorySize=335544320`; `tools/check-package-flexible-memory.py` checks metadata. Does **not** supply on-demand guest/JIT allocation and is not proof of more available GPU RAM. |
| P0 GPU | Maintained Vulkan emulator renderer source | **Selected for build** | `headless/vulkan.cmake` copies `vendor/encore-active/eden-vulkan` into generated native compilation units; `tools/check-vendored-vulkan-fork.py` checks transformation-oracle/source identity against pinned Eden + shipping backports. Does not certify all newer independent upstream graphics commits. |
| P0 GPU | Guest CPU writes / buffer coherence | **Instrumented, not established corrected** | `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp` takes the buffer mutex when pages were registered and invalidates texture/shader state. The newer `EDEN_GUEST_CACHE_LOCK_TAIL` observes >1 ms and >10 ms waits without removing locks; no fresh real-game trace has established its actual long-tail distribution. |
| P0 GPU | RADV native binary source provenance | **Selection known; complete current-source parity not proven** | `headless/vulkan.cmake` links `build/radv-isolated/libvulkan_radeon.ps5.a`. `tools/deps.json` pins Mihawk's Mesa `0b2d6d1` and Vulkan tools `3f3ee69`. A source pin alone does not show the actual binary was produced from all desired/latest Mihawk commits; audit the archive's build recipe/hash before claiming that. |
| P0 shader stutter | Fast-first graphics pipelines | **Adapted, default ON only in dev builds; OFF in ordinary builds** | `headless/main.cpp` recognizes `fast_pipelines=on/off`; `headless/dev_vulkan.h` initializes `fast_first_pipelines=true` under `EDEN_DEV_PROFILE`, `false` otherwise. Mihawk reports 32% less draw wait in one cold-cache game. That measurement is **not** FC27 or Encore proof. |
| P0 shader cache | Persisted native graphics cache | **PS5 credential guard already adapted; cache hits unproven** | The **active** `vendor/encore-active/ps5-mesa/src/util/disk_cache_os.c` bypasses `__normal_user()` only under `__PROSPERO__` (ported from mpereiraesaa); its ordinary-host protection and cache-disable variables remain in place. `tools/check-ps5-mesa-shader-cache.py` exercises both variants. A configured cache directory still does **not** prove writes/hits or eliminate shader-related stutter. |
| P1 GPU | HUD counters | **Launcher/emulator HUD distinct from game's HUD** | ProsperoEden's newer per-core FPS/HUD source changes concern the emulator overlay. The player's complaint about an **in-game HUD updating late** concerns guest-generated draw/state freshness and is not fixed by changing overlay display fields. |
| P1 CPU | A32 fastmem | **Selected / pinned-file parity** | `headless/checked-fastmem.cmake` matches upstream, A32 alias is separate from A64. |
| P1 CPU | A64 fastmem | **Not a validated shipping shortcut** | Mihawk's `docs/PERFORMANCE_FINDINGS.md` reports checked A64 fastmem working but lower FPS in one game due to kernel wait behavior. Do not assume enabling it fixes FC27. |

## Why our previous conclusion was too strong

The latest available 415-window match telemetry is from `2efd8b3c`,
not from the new modifications. It documents 858 frames >50 ms, 10 >500 ms,
and a prolonged content/progression stall while the compositor stays active.
It **cannot** establish whether later source changes improved or worsened FC27.
The host/GPU stress replays prove bounded queues preserve behavior under
synthetic load, not that in-game frames or saved controls progress correctly.

The latest native diagnostic run `38545198780` **failed to compile** in
`headless/performance.cpp` (attempted atomic `exchange()` on a const
counter). Commit `aac065ab6045e8a3ce90d2cfb09eeb08c0c8a6cf`
changes this to a mutable local reference. The fix is **source-corrected but
not yet validated by a successful native run for that SHA**. No claims of a
new green console candidate should be made for this particular change.

## Priorities and qualifying gates

1. **CPU/HLE — actual guest progress and synchronization.**
   Capture wait reason and owner/callee for title threads around the freeze.
   Counter increments for IPC and draws are not proof of game progress. Keep
   lock ABI unchanged unless trace shows a specific waiting cycle.
2. **GPU — in-game content freshness, cache and shader cold starts.**
   Correlate >50 ms frames with buffer lock outliers, shader pipeline
   compilation/first-use, and GPU fence waits. Distinguish generated content
   versions from frame presentation counts. Verify **actual Mesa disk cache
   activation** before changing rendering or process privileges.
3. **JIT — classifying costs before new compilation strategies.**
   Record per-core JIT compile counts/durations, page commits, cache
   evacuations and generated block hotness. Compare startup (<6k frames)
   against sustained gameplay (6k–32k). Do not mistake a window's JIT time
   for a single frame's stall.
4. **Potential adaptive compilation — only as an isolated experiment.**
   Keep ordinary Dynarmic stable. On an independently built development
   variant, measure baseline block compilation first; then evaluate a
   two-tier policy (fast cold compile, bounded background optimization of
   hot blocks) with immutable build flags and strict eviction/invalidation
   and resource limits. Cross-core shared compilation and asynchronous
   code patching need fresh concurrency and executable-alias validation;
   neither can be activated merely because Java has a tiered JIT.
5. **Memory — qualified subsystem changes, not one giant cherry-pick.**
   Compare guest lazy backing, JIT incremental code commitment, sparse page
   tables and free direct/flexible memory independently. Preserve fail-closed
   startup and per-page alias lifetime guarantees.

**Integration audit limitation:** this inspection compares named high-impact
source locations and production wiring; it is *not* a file-by-file evaluation
of every commit in every external repository previously discussed (including
independent experimental forks). The upstream gap register documents divergent
Mesa and SDK histories, and GitHub changed-file results may be truncated.
No FC27 save data or console file was read or modified.

## Corrected native cache integration audit

**Correction to the earlier conclusion:** the plain pinned Mesa code requires
`geteuid()==getuid()` and `getegid()==getgid()` before accepting disk
caching. But Encore does **not** compile that unmodified policy on PS5.
Its actual production source
`vendor/encore-active/ps5-mesa/src/util/disk_cache_os.c` includes a
selective `#if !defined(__PROSPERO__)` guard around the
`__normal_user()` rejection. That adaptation was already present, came
from `mpereiraesaa/PS5_Mesa`, and is proved against the immutable source by
`tools/check-ps5-mesa-shader-cache.py` (including native/host C sanitizers).
Changing the process group via `setegid(getgid())` is **not** an identified
missing correction for Encore. The earlier claim based only on
`vendor/sources/ps5-mesa` was mistaken.

The new one-time `EDEN_GPU_DISK_CACHE_CONTEXT` marker logs UID/GID match
flags, cache-directory presence and existence of a disable environment
variable. On this driver, mismatch alone is **not** interpreted as a cache
rejection. The parser `tools/check-native-shader-cache-eligibility.py`
checks the exact native source bypass, treats absent events as
**NOT_MEASURED**, and never claims shader cache hits from the configuration.
It makes **no credential change or filesystem mutation**.

The `2efd8b3c` capture only contains
`EDEN_RADV_DISK_CACHE limit_mib=2048 free_mib=16384`, which cannot
confirm shader cache hit rate. A genuine shader hit/miss or cache-file
reuse probe is still needed if shader compilation remains a bottleneck.

Build qualification: run `38547995294` completed successfully and
uploaded the native test package and symbols before the new context
marker. The later marker must pass its own source preflight and native
compilation; there are no new console performance measurements.

## Lessons for the upstream adaptation audit

Never infer what Encore runs solely from the original immutable
`vendor/sources/` snapshot. For each relevant fix, compare
**original source → `vendor/encore-active/` compiled source → concrete
CMake/native build path → source/host test → runtime trace**. In this
case the existing test `check-ps5-mesa-shader-cache.py` was stronger
evidence than either the documentation or the original Mesa source.


## Full native graphics archive provenance (follow-up)

A second source-to-binary integration gap was found in the build scripts.
The original native archive reuse check in `tools/prepare-build.sh` checked
only the pinned Mesa revision and the adapted **WSI** source hash
(`EDEN_WSI_SHA256`). It did not compare the other ten patched Mesa inputs,
including `src/util/disk_cache_os.c`. Thus an archive could be linkable but
still contain an outdated translation unit even while the source tests passed.

The corrected build now fingerprints **all eleven** maintained files listed
by `tools/install-vendored-radv.py::PATHS`; the deterministic SHA256
includes relative paths, lengths and file digests. Only the second,
successful native driver compilation can write
`EDEN_ACTIVE_INPUTS_SHA256`, after verifying every staged source matches
the maintained tree. Missing or mismatched stamps force regeneration and
discard any old isolated archive. `tools/radv-active-inputs.py --self-test`
individually mutates each of the 11 paths to prove all invalidate reuse.

Also, `install-vendored-radv.py` now refreshes the modified file's mtime
after atomic replacement. Preserving the *original* source mtime with
`copy2` could make an older source file appear older than Ninja's
compiled object, preventing recompilation even after bytes changed.
`check-vendored-radv-fork.py` now verifies the actual post-install mtime
change with a deliberately stale test input.

This **strengthens compiled-source selection**, not emulator performance.
The first cold reconstruction of the native driver may be slower. No new
FC27 match demonstrates any FPS or texture change, and the new source
fingerprint guard still requires CI and native build qualification.
