# Eden Encore — final engine-owner audit, single shipping profile

**21 October 2026**. Engine source triage is not synonymous with "everything became faster." The three remaining active source owners have been reviewed against existing pinned sources, CMake selection, scheduler/HLE relationships and host tests. We do **not** make speculative code edits before a single console test. Source SHA-1 Git blobs are frozen by `tools/ci/check-final-engine-owner-contracts.py`; editing any one of them must reopen the review.

| Source | Decision | Git blob |
|---|---|---|
| `vendor/encore-active/eden-core/src/core/hle/service/sm/sm.h` | **Keep as integrated**. The existing backport copies the factory under the registry lock, invokes it outside the lock, and distinguishes 1 ms host-dummy wait from guest SleepThread. This avoids the original host-worker SVC deadlock. Event-driven wakeups would require modifying the paired RegisterService implementation and broader lifecycle testing; changing the polling interval now would trade responsiveness for wakeups without measurements. | `83e0b7e26a867d578eb869389a807fe3b9c7035b` |
| `vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.h` | **Keep as integrated**. The header's cross-thread `std::binary_semaphore` permit is paired with `k_scheduler.cpp`'s acquire/release and selected together under `EDEN_BLOCKING_GUEST_CONTEXT_LOCKS`. Standalone changes to thread ABI, suspend flags or atomic ordering are unsafe. | `e2f359a54cb6b879bdd41f092cf1ea19fb03e4e6` |
| `vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp` | **Keep as integrated**. The standard A64 path is selected over shared JIT in release. Compile batching and phase diagnostics are guarded; range overflow escalates to full invalidation, and invalidation owns its mutex and resets RSB. Existing host witnesses cover cache lifecycle; no additional safe performance improvement was identified without PS5 traces. | `20362a046adfe89d65225c1822104f2910eeb2c5` |

Existing evidence: `tools/install-active-core-backports.py`, `tools/verify/hle/check-hle-overlay-layout.py`, `tools/check-native-hle-suspend-noop-host.py`, `tools/check-maintained-a64-interface.py`, `tools/check-native-a64-cache-invalidation-host.py`. New contract `tools/ci/check-final-engine-owner-contracts.py` asserts current source SHAs, build selection and corresponding runtime ownership.

**Coverage: 429 of 491 source files classified and handled. Engine unexamined: 0. Launcher UI sources: 62 (separate).** Only the previously edited sources are counted as code optimizations. These three count as *audited, retained without further edits*, not FPS wins.

**Release remains blocked from final console qualification** until HEAD host preflight, fast gate and CodeQL are green and a complete native PS5 package is compiled. A host source audit cannot validate actual GPU/frame pacing or the user's game freezes.
