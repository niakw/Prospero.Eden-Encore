# Eden Encore — PS5 experimental test gate after R282 (2026-10-10)

This checklist applies exclusively to `dev/ps5-sparse-jit`. It is **not** a shipping or stable-release certificate.

## Confirmed in GitHub source / host tests
- R270–R279 direct-memory ownership, non-releasing heap-reuse model, guarded direct-memory probes, Vulkan texture-GC prefetch and pool capacity contracts: host green.
- R280: Vulkan PresentManager tracks the dequeued-but-in-flight frame and propagates presentation-worker errors. [Host green #38067528391](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38067528391).
- R281: GetRenderFrame releases free-queue mutex before a potentially blocking GPU present fence. [Host green #38067761638](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38067761638).
- R282: production `prepare-vulkan-port.py` header/CPP present-manager replacements **replayed in exact sequence** on upstream Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a` sources, both verified by Git blob hashes; [host green #38068514459](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38068514459), with `VULKAN_PRESENT_SOURCE_REPLAY_PASS` and `CORE_PREFLIGHT_ALL_PASS`.
- Native PS5 build was **SKIPPED** for the above host runs. Host test mocks are not the real RADV renderer or Sony SDK.

## The next legitimate step: one controlled **native developer test build**
- GitHub workflow: `.github/workflows/build-040-zbic.yml`, development branch `dev/ps5-sparse-jit`.
- Use one deliberately triggered **all-on test** (`test_all_on=true`, `publish=false`, `build_only=false`, `test_title_id=0100C49025D3E000`) on the development branch. Never target `fix/0.40-zbic-13.60`.
- Do **not** bypass full native preflights. The R282 pinned Vulkan replay and R280 concurrency test are now native-preflight blockers before SDK compilation.
- Do **not** push source changes while native workflow is active: GitHub Actions uses `cancel-in-progress: true` for this branch.
- Only call the candidate installable if native source preparation, PS5 compilation/link, staged-app binary validation and artifact upload all **SUCCESS**. A host-only green check is insufficient.
- Capture the GitHub run ID, Git SHA, native unstripped ELF/symbols, staged binary SHA256 and `crash-provenance.json`; do not publish a production release.

## Firmware 13.60 hardware acceptance test (after build artifact exists)
1. **Launcher**: load without `std::bad_alloc` or SIGSEGV; verify FC27 and BOTW listed; rapid long-press navigation and Home hero title not truncated; input mappings are PlayStation and exit/relaunch is deterministic.
2. **FC27 cold**: start menu and a full gameplay segment; note first texture correctness, black/pink/unmapped regions, video intro hitch, FPS average/minimum and max frame interval (ms). Keep the complete log and note elapsed runtime until crash/freeze.
3. **FC27 warm**: close and reopen same title *within the same launcher process*, repeat equivalent scene; compare cache effects and GPU stall counters, not just displayed 30 FPS.
4. **BOTW**: same launcher process after FC27; watch Ultra-profile texture correctness and smoothness and any degradation across title switch.
5. **Memory/lifetime**: compare `EDEN_DIRECT_POOL_OWNERS`, `EDEN_HEAP_LIFETIME`, `EDEN_HEAP_RETENTION`, JIT committed/reserved and largest kernel-confirmed free block at core init, shutdown and destroy. Expect possible persistent 1,280-MiB root ownership; do **not** mislabel it as firmware OS reserve or claim it was reclaimed.
6. **Timing**: collect existing `EDEN_VULKAN_TEXTURE_BUDGET`, GPU present/fence wait, worker topology, guest faults and frame-window diagnostic markers when available. Keep expensive `memory-region-scan.txt` **absent** for the normal performance run; use it only for a separate diagnostic audit.
7. **Failure**: preserve full boot trace, stderr, heap and crash reports; compare against the same-build ELF/symbol hash; do not assume a lower FPS counter means a GPU sync fault.

## Unresolved, **not requirements to prove resolved before this first diagnostic test**
- Actual FC27 0-FPS/black texture/fault causes and long-term crash stability.
- Native sparse RX/RW executable mapping and JIT lifetime on firmware 13.60, beyond host mocks.
- Native CPU/GPU utilization and any real millisecond/FPS improvement from R276–R281.
- 1,280 MiB of Encore-owned physical Sony heap roots retained for reuse; no proven safe Sony mspace quiescence/destroy-and-unmap protocol.
- Kernel-exposed 12-GiB direct extent is not guaranteed free and is **not** permission to use Sony-reserved portions of 16 GB installed GDDR6.
- BOTW/FC27 in-game PlayStation glyph coverage and any game-specific atlas still need on-console qualification.

**Decision:** source branch is ready to **attempt a controlled native all-on development build**, then perform a **diagnostic hardware test**. It is NOT rated stutter-free, texture-complete, resource-maximized, or final-shipping-ready.
