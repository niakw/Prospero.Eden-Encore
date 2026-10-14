# Console regression evidence — 2026-10-14 (firmware 13.60)

> Scope: trace supplied by the tester, not a reproducible host benchmark. The CI build being green certifies packaging/static checks only, **not** console frame pacing, graphics correctness, gameplay remapping or liveness. Do not mark those four defects fixed without on-device evidence.

## Tested package provenance

- Native release run: [38639342063](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38639342063), successful.
- Installed executable: `b83305b2c397392e27582587bd3a4f4347f1ba51` (`EDEN_BUILD_SOURCE`, `EDEN_SESSION_SOURCE` and boot trace agree).
- Firmware: 13.60. Native title: `PPSA99008`. Guest title: `0100C49025D3E000`.
- Console evidence supplied: `boot-trace(20261014-221025).txt`, `heap(20261014-221025).log`, `stderr(20261014-221026).log`, `network-accepted(7).log`. Earlier, different-profile diagnostic traces: `heap.prev(9).log`, `stderr.prev(9).log`.

## Shipping-release observations — exact b83305b executable

- From 87 consecutive ~5-second `EDEN_VULKAN_FRAME` reports: mean **28.92 FPS**, median 30 FPS, minimum **18.087 FPS**; 8 windows below 25 FPS, 59 near 30 FPS. Worst individual recorded frame **1233.472 ms**; 39 `late100` and 6 `late500` across these windows.
- Internal Vulkan framebuffer `2560x1440`; configured session used 1x bilinear, FXAA, 1440p output at requested 60 Hz (native presentation reports 59.94 Hz). Do not attribute the long stalls to upscaling or shader cache alone.
- Native allowed mask `0x1fff`: 13 available logical CPUs. Both read-only FreeBSD topology OIDs returned ENOENT (errno=2). AMD CPUID appears as 13 distinct physical IDs, x2APIC as one ID. **Neither is trustworthy**: `EDEN_WORKER_TOPOLOGY ready=0`; no physical-core pinning was qualified. Do not synthesize SMT siblings.
- The release logs `SCHED_FIFO` at native priority 700 and `rr_attempted=0`. An older developer-profile sample successfully used `SCHED_RR` at the same priority. This is a configuration difference, **not** a matched FPS or freeze A/B.
- The release reports `EDEN_FRAME_PRESSURE` zeroes because detailed counters were not enabled in shipping code. **Zero is not evidence of no guest IPC/JIT/GPU work**.
- Controller: `EDEN_PAD_MAPPING_FIXED ... title_override=1 own_mapping=0` and `game_action_profile_observed=0`. `own_mapping` refers to Encore's launcher per-title *physical-to-guest* mapping, not the guest title's in-match action bindings. The guest's save/profile loading is not qualified. The native pad continues receiving samples and reports zero poll errors.
- No causally decisive OOM marker was observed. Native/network audit reports repeated blocked guest domain requests, some `target=[2a02` entries are truncated; blocked DNS requests alone do **not** establish the stutter cause.

## Previous diagnostic trace (different build/configuration; do not mix with release)

- 207 five-second frame windows across two sessions: mean 27.94 FPS, minimum 14.864 FPS, worst recorded frame 2659.936 ms. Not a controlled comparison to b83305b.
- The first session ended with `EDEN_STAGE phase=guest_fault`; stderr identifies **`guest thread MuseLogicThread_match jumped to an unmapped address`**. This is a verified guest prefetch-abort symptom; it does not yet distinguish a JIT/corrupted branch target from guest/application memory misuse.
- A separate recorded `kernel.SuspendEmulation(true)` call took **134131 ms**, with later waits of 2248 and 4235 ms. The method name alone does not establish the exact cause of the delay; investigate the calling path and wait owner.
- A late five-second detailed window around frame 22865: `gpu_idle_ms=3729.615`, `gpu_dispatch_ms=1258.227`, `gpu_fence_ms=3.214`, `guest_ipc_ms=560.320`, `cache_wait_ms=104.493`, `jit_ms=0.458`. These are overlapping subsystem elapsed-time counters; do **not** add them into one frame budget. They point away from a permanently compiling JIT or consistently GPU-saturated renderer.
- For the five instrumented drop categories (`no_pipeline`, `configure_rejected`, `built_pipeline_failed`, `descriptor_buffer_full`, `worker_pipeline_failed`) the reported `total` remained zero. This does not prove texture/cache coherence or correct HUD presentation.
- The developer test reserved ~2.32 GB sparse JIT VA with on-demand committed pages; the shipping release used ~2.33 GB dense JIT allocation at game load. Different modes, with problems described in both. Do not presume a larger JIT cache solves them.
- The controller values `polls=195000 samples=520960` in the release stderr are cumulative native poll/read-sample counts, **not controller actions**. The same last heartbeat reports `edges=638` physical state transitions. At an approximately 4ms poll interval, 195000 polls correspond to roughly 13 minutes of controller-worker activity, but without timestamps per heartbeat this is only an estimate.
- The explicit unmapped-guest-execution fault is in `stderr.prev(9).log`, line 334: `MuseLogicThread_match jumped to an unmapped address`. It is **not** established for the b83305b release from its truncated stdout/heap trace; GPU unmapped-address counters do not cover this CPU prefetch-abort path.
- Heap diagnostics showed `failures=0` in the observed snapshots; absence of allocation failure does not rule out wrong guest memory mapping.

## Required engineering order before promising another console improvement

1. **Guest execution and genuine freeze:** use the already-implemented fatal-path `pc/lr/sp/fp/tid` capture when a new mapped/unmapped fault occurs, and distinguish a running GPU/pad heartbeat from actual *guest* progress. Do not auto-retry an invalid jump.
2. **Native scheduler contention:** investigate equal-priority native `SCHED_FIFO` and physical topology rejection. A bounded RR comparison is possible because older DEV logs show successful readback, but no performance win is established, and changes must remain fail-open.
3. **Graphics/HUD:** instrument resource-version/guest-write visibility at actual HUD upload and draw, and discriminate texture reupload vs descriptor/alias vs presentation lag. No draw-drop counts does not validate pixels.
4. **Guest IPC/network:** correlate recurring blocked guest requests with per-command IPC latencies on the same monotonic clock before changing DNS responses or network policy.
5. **Guest-owned controller settings:** trace guest title save/profile load and the HID reports it receives. Do not mistake a launcher mapping for the game's match-action assignment.
6. **Regression gates:** retain code SHA, title ID, timestamp anchors, accurate `not_measured` states for disabled release diagnostics; publish an installable artifact only after host checks and mark hardware quality separately.

### Upstream candidates not yet performance-qualified on this firmware

- [#187](https://github.com/blackbearreloaded/ProsperoEden/pull/187) deferred GPU-cache writes: promising on its author's hardware, but measured cache-lock waiting in the late sample above is not sufficient by itself to explain all freezes; synchronization changes could affect coherency.
- [#185](https://github.com/blackbearreloaded/ProsperoEden/pull/185) partial texture-row uploads: benefits large repeatedly updated textures, but this trace does not isolate that path as the HUD defect. Must preserve page-tracking balance and whole-upload fallback.
- Do not claim either patch resolves the reported title. They were not applied as part of this audit.

## Status

**Console gameplay: FAIL / unresolved.** **Packaging/CI: PASS** for `b83305b`. No evidence-based performance or gameplay fix is claimed by this document. Keep the current single development branch and do not invalidate the in-progress native build with an unrelated `[full-build]` commit.
