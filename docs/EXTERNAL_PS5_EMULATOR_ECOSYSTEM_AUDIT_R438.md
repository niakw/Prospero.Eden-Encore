# External PS5 emulator/runtime audit — 13 October 2026 (R438)

**Scope:** Re-check `mpereiraesaa/prospero-win` including `docs/WINE_PS5_BUILD.md`; compare related PS5 native emulators/drivers, the current `blackbearreloaded/ProsperoEden` main branch and `niakw/Prospero.Eden-Encore` (`dev/ps5-sparse-jit`, R438). This is a **source audit only**. It does **not** qualify a binary or make claims that FC27/HUD defects have been fixed. Do not create extra development branches.

## New, confirmed omissions

### 1. Texture garbage-collector traversal budget (**HIGH**, not in Encore R438)

- Source: [ProsperoEden commit 46b269f, 2026-10-13](https://github.com/blackbearreloaded/ProsperoEden/commit/46b269fc1821), `tools/check-gc-scan.py`, `tools/prepare-vulkan-port.py`.
- Issue: upstream Eden uses `num_iterations` for **visits**, including textures skipped because they are expensive, decoding or too dirty to evict. A group of protected textures can exhaust this budget before the collector reaches evictable entries.
- Upstream adds separate `num_scanned` (max 8192) and decrements the eviction budget only when actually proceeding with an eviction; opt-out `gc_scan=upstream`. An aggressive pass resets the scan counter. This is **not** the same as our existing `gc_keep_dirty`, which changes the criterion for keeping GPU-written textures.
- Encore audit: `tools/prepare-vulkan-port.py`, `headless/performance.h` and `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h` contain **no** `gc_count_visits`, `num_scanned` or `max_scanned`; R438 still has `if (num_iterations == 0) return true; --num_iterations;`.
- Recommendation: port upstream's complete, **separate** scan and eviction budgets with strict source anchors and an opt-out flag, a host test including >budget ineligible images, and **detailed** counters `visits / skips / evictions`; do not claim this resolves HUD flicker without validating alias/fence/target freshness. This is newer than our previous Oct 13 d7f2764 port.

### 2. Vulkan/RADV revision check (**HIGH** for driver verification)

- Encore's `UPSTREAM.json` pins `ps5_mesa_commit=0b2d6d1a61d9bbf89cf8beb88a696144f67c61f8` (2026-09-30) and `ps5_vulkan_commit=3f3ee69607013b345d2baa6d6a37c86745649a08` (2026-10-01, Mihawk branch).
- Mihawk's [PS5_Vulkan commit 252bf912](https://github.com/mihawk-99/PS5_Vulkan/commit/252bf912a745) pins PS5_Mesa `47e9eb61ee7e1112194557e1e047178562827bc6` (2026-10-10). The WSI previously treated `sceVideoOutIsOutputSupported(15)==0` as support for 119.88 Hz, falsely reporting 120 Hz when the output remained 59.94 Hz. The fix requires support > 0, a successful mode switch, and actual vblank validation.
- This **does not prove** R438's RADV is wrong at 60 Hz or that 30 FPS flicker is a WSI bug; Encore's `headless/display_refresh.h` and `tools/package-headless-native.sh` already have a 120 Hz request path. Audit the staged **binary driver** revision, not only manifest metadata, plus buffer format/alias/blit/swapchain issues in the intermediate PS5_Mesa commits before changing versions.
- Source: [Mihawk HARDWARE_FINDINGS](https://github.com/mihawk-99/PS5_Vulkan/blob/main/docs/HARDWARE_FINDINGS.md), [prospero-win Wine PS5 Vulkan section](https://github.com/mpereiraesaa/prospero-win/blob/main/docs/WINE_PS5_BUILD.md#vulkan).

### 3. Native PS5 scheduler and worker fairness (**HIGH**, read-only evidence first)

- [prospero-win Wine patch 0881](https://github.com/mpereiraesaa/prospero-win/blob/main/docs/WINE_PS5_BUILD.md#patch-series) reports **13 permitted CPUs**, not the 16 online on the author's console. It identifies busy SCHED_FIFO threads of equal priority not yielding when too many workers run. Patch 0882 experiments with `SCHED_RR` and priority bands, behind `WINE_PS5_SCHED=1`.
- Encore already detects `cpuset_getaffinity`, prints `EDEN_PS5_THREAD_SCHED` once per thread, constrains JIT/shader placement, and does not overwrite the policy. It **does not currently set a verified SCHED_RR policy** for its relevant threads. This is a meaningful unresolved lead for a 30 FPS plateau with persistent guest mutex contention, not proof FIFO is the actual firmware 13.60 root cause.
- Compare `EDEN_PS5_THREAD_SCHED` per role; only then test a reversible small-scale policy switch with verified priorities and affinity masks. Do not globally increase workers to 13 or 16 or infer SMT physical grouping from the logical mask.

### 4. Pipeline compile lock separation and frame-correlated diagnostics (**HIGH** for spikes)

- [prospero-win #676](https://github.com/mpereiraesaa/prospero-win/pull/676), commit `297c1477f4c8`, found **300–500 ms frames** in GTA IV from multiple DXVK compiler threads serializing behind a single Wine Vulkan PE stream gate. It drains pending work under the gate and moves `vkCreateGraphicsPipelines`, `vkCreateComputePipelines`, ray tracing pipelines and shader objects outside it.
- Encore R421 prioritizes *cold first-use graphical shaders* against speculative optimizer work; that is **not an equivalent proof** that our graphics-cache mutex, worker enqueue gate or GPU command scheduler never serializes compilation under a shared lock.
- [prospero-win's frame CS profile](https://github.com/mpereiraesaa/prospero-win/blob/main/docs/cs-thread-profile.md) correlates **same-frame** present time, per-thread runtime/driver times, Vulkan API calls, slow calls and command-stream types. Encore logs 5-second aggregates and some subphases; add a **bounded** slow-frame-only correlation keyed by frame/guest thread ID, and make logging opt-in. Validate whether guest simulation advances on visually frozen frames.
- Not portable literally: Wine's PE stream gate and DXVK are not in Eden; only the concurrency principle and measurement approach transfer.

### 5. Input/event notification and menu-pause hang (**HIGH** diagnostic)

- Wine's patch `0879` documents a **stale wake-pipe/GUI event state** that caused a game to stall while a button was held, even though the input path ran. It is an analogy, **not** a proven FC27 fix.
- R436 added `EDEN_NPAD_PLUS_LIFO` and `EDEN_NPAD_PROGRESS` to witness guest Npad memory writes after Options-to-Plus publication. Before changing mapping or generating presses, inspect the guest `Npad` LIFO update and HID/IPC wait consumers, including the **age/sequence** of data and event-notification coalescing when Pause is opened.
- `prospero-win` also implements a guarded key-state shared path ([docs/shared-input-fastpath.md](https://github.com/mpereiraesaa/prospero-win/blob/main/docs/shared-input-fastpath.md)), but it explicitly leaves async key reads on the original event-pumping path. Never substitute cached key state for a side-effectful event read.

### 6. HUD / texture fidelity: avoid wrong DXVK shortcuts (**MEDIUM**, fidelity first)

- [prospero-win-profiles README](https://github.com/mpereiraesaa/prospero-win-profiles) describes DXVK `d3d9.asyncSmallReadback=True` (reads previous-frame result), `d3d9.padVsOutputs=True`, a weaker render-target submit hint, and fast-linked shaders. These are **Direct3D9 semantics**, not settings we can paste into Eden's Vulkan emulator.
- An intentionally stale readback is **not a sensible default for FC27's disappearing score/timer HUD**. Instead build a render-target/descriptor/alias/fence witness for the exact affected frames and compare checksums or captured pixels from known stages (when a supported capture mechanism exists). `EDEN_GPU_DRAW_DROP=0` only excludes some outright draw failures, not incorrect descriptors.
- PS5SX2 ([Swordpdf/PS5SX2](https://github.com/Swordpdf/PS5SX2), `ps5/README.md`) runs **PCSX2 on PS5** using a *different* modified ps5vk driver; it demonstrates host-native JIT and PS5 GPU feasibility, but is not evidence to replace Encore's RADV or game texture correctness without API-specific integration tests.

## Other relevant differences

- [ProsperoEden #152](https://github.com/blackbearreloaded/ProsperoEden/commit/7215d23bcb8b): newer `attribute3` declaration uses VRR bit 18 rather than bit 19 (firmware 6.02 treats the latter as unknown); Encore's native packager currently forces `0x80040` (120 Hz plus newer VRR bit), not `0x40040`. Investigate compatibility on **FW 13.60** and actual TV capabilities before changing the declaration. Declaring VRR does not increase a 30 FPS game's true simulation speed.
- [ProsperoEden #139](https://github.com/blackbearreloaded/ProsperoEden/commit/b84c95b93854): on a **PS5 Pro** an `attribute3` flag `0x400000` enables a direct-memory pool measured at 13,504 MiB, versus 12,288 MiB on base PS5. Physical 16 GiB RAM is **not** a 16 GiB title-owned pool. Encore already calls `sceKernelGetDirectMemorySize` in its memory management; don't assume unreserved OS RAM can be made available simply by enlarging JIT caches.
- Wine patch 0150 measured ~3.3 ms per PS5 `write()` independent of size and batches registry saves in 1 MiB chunks. Encore's R428 rate-limits guest-error log flushes, but this suggests an independent review of small file writes in telemetry/cache and session-save paths; don't hide crash logs by over-buffering.
- [Mihawk PS5_Vulkan](https://github.com/mihawk-99/PS5_Vulkan) supports hardware probes with host replay and pixel/readback reference controls. Our source-only and sanitizer tests validate internal contracts, not the actual screen image. Favor a minimal HUD pixel/descriptor comparison on native hardware before speculative rasterizer settings.
- The newly surfaced [PS5SX2](https://github.com/Swordpdf/PS5SX2) supplies a second native emulator case study, but its PCSX2-specific GS and PS5HB_Vulkan changes cannot simply be imported.

## Recommended order / stop conditions

1. **Audit and port the texture GC scan-liveness fix** independently of existing `gc_keep_dirty` and buffer-page R437; strict fallback flag + host-source and native integration tests. Avoid unproven claims about HUD.
2. **Audit staged RADV/Mesa build against pinned versions** and bring forward verified WSI fixes only after comparing driver APIs and framebuffer/readback tests.
3. **Frame-correlated bottleneck instrumentation:** combine GPU frame ID with emulator guest/JIT progress, buffer mutex waits, pipeline waits, HUD descriptor/alias updates, and confirmed Npad LIFO. Keep bounded/on-demand to avoid skew.
4. **Scheduling proof:** compare FIFO/RR/affinity measurements at rest vs in-play with a reversible A/B; preserve the default if CPU starvation is not demonstrated.
5. **HUD correctness:** inspect and record render-target, alias and texture rebinding at actual failure, rather than weakening fences or enabling one-frame-late readback.
6. Maintain **single** branch `dev/ps5-sparse-jit`; don't create temp branches and don't trigger a new native compilation for audit-only documentation.

**Evidence limits:** External title FPS numbers (GTA IV, HL2, PS5SX2) are not forecasts for FC27. Driver experiments from FW 12.02 / 13.40 cannot automatically be assigned to FW 13.60; host preflight success is not a hardware graphics-quality measurement.

## R440 correction and ecosystem expansion (13 October 2026)

**Acceptance policy:** A properly scoped native result from the upstream author is sufficient to *start porting* a compatible change. Do not demand another user PS5 run before implementation. An author's hardware test cannot certify an Encore-specific integration; source/CI checks and a consolidated later console test still apply. No automatic native build is implied.

### Factual correction to R438

The official Mihawk PS5_Mesa high-frame-rate offer/configure fix **was already ported in R400**: `tools/patch-radv-wsi.py` and `tools/check-ps5-videoout-120hz-offer.py` prove its presence, and the active source reports `supported > 0 && configured == 0`. The manifest remains pinned to the older Mesa commit deliberately. R438's *driver revision comparison* remains worthwhile, but it is wrong to imply that particular WSI 120 Hz fix is still absent.

### Integrated, author-qualified adaptation — Pereira WSI

- Source: [mpereiraesaa/PS5_Mesa f2ee3891](https://github.com/mpereiraesaa/PS5_Mesa/commit/f2ee3891be81f5f36fc1e64ada36e36033bae5e4). His PS5 Wine/Zink report concerns a hidden swapchain blocking the real window. The fix's host-model tests demonstrate takeover, retirement, presenting and release; the exact new version is not documented here as validated on console.
- R440 ports the narrow `presented`/handover logic into the **existing fixed-resolution, single-scanout Encore RADV WSI**, *not* the author's entire variable-size WSI. It also patches the archived generator and checks for conflict both before and after image allocation. The winning swapchain owns presentation; the displaced one is retired; last-owner teardown remains Encore-owned.
- Gate: `tools/check-ps5-videoout-unpresented-takeover.py`, with state matrix and active-source anchors. This is **source-only**: no claim that FC27 HUD, texture or pause freezes are fixed.

### Further relevant upstreams

- [Swordpdf/ps5-framegen](https://github.com/Swordpdf/ps5-framegen): reusable Vulkan interpolation and guest-tick-based pacing, already exercised in PS5SX2 on ps5vk and RPCS3-PS5 on RADV. A credible later *presentation* enhancement; generated frames do **not** unblock game simulation, HID/HLE waits or source texture corruption. Integrate source and shaders with provenance before wiring to Encore's present queue; do not claim it is active merely by vendoring it.
- [drakmor/ps5-hwinfo](https://github.com/drakmor/ps5-hwinfo): system CPU clocks and idle-delta load; a payload has different permissions/lifecycle than a title, so cannot simply call every API from `eboot.bin`.
- [drakmor/ps5-native-gamepad-input-research](https://github.com/drakmor/ps5-native-gamepad-input-research): device-tested `scePadRead` batching/timestamps; Encore `headless/pad.cpp` already consumes each batch, so do not reimplement that.
- [ArkSama/PS5_RPCS3](https://github.com/ArkSama/PS5_RPCS3): emulation architecture reference; RPCS3 GPL-2.0-only and RetroArch GPL-3.0-or-later distribution restrictions demand separation before copying source.
- [ArkSama/Unlock-ps5-pro-memory](https://github.com/ArkSama/Unlock-ps5-pro-memory): title attribute3 bit 22 qualifies ~1.19 GiB extra direct pool on **PS5 Pro**, FW13.60, but does not give additional RAM to Encore's base PS5.
- [EchoStretch](https://github.com/EchoStretch/kstuff-lite), [soniciso1](https://github.com/soniciso1/ps5-linux-archive) and [ntfargo](https://github.com/ntfargo/Relapse-Exploit): useful kernel/loader/firmware evidence, not portable Vulkan or emulator FPS patches by themselves.
- Mesa outside GitHub: [RADV documentation](https://docs.mesa3d.org/drivers/radv.html) separates application SPIR-V, NIR/ACO compilation, userspace winsys and privileged GPU submission. [Mesa 26.2 release notes](https://docs.mesa3d.org/relnotes/26.2.0.html) include shader/image/format fixes but require cherry-picking onto PS5 fork, not wholesale desktop driver replacement.

**Follow-up priorities:** bounded same-frame simulation/lock/present correlation; descriptor/alias/HUD freshness; independently vetted WSI variable swapchain sizes; controlled native worker scheduling; full optional Swordpdf framegen present path, after the core's stalled frames are identified. Do not block source ports on repeated user tests.
