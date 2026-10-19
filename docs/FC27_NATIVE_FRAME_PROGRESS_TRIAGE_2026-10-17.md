# FC27 native frame-progress triage — 2026-10-17

**Evidence:** user-provided `heap(20261015-161206).log` dated
2026-10-15. **Session renderer: Vulkan** (log includes
`EDEN_STAGE backend=Vulkan` and the matching native Vulkan
frame/pressure diagnostics). The console additionally initializes
OpenGL/Gallium for display; that does not redefine the title renderer.

## Exact offline pairing

232 `EDEN_VULKAN_FRAME` intervals have 232 matching
`EDEN_FRAME_PRESSURE` intervals by total frame number.
All are aggregate reporting windows, typically ~5s.

- 192 windows hold ~30 FPS with `worst_ms < 50` (median JIT
  compilation 0.213ms, median aggregate cache wait 17.255ms).
- 13 windows contain a frame of at least 300ms (median JIT compilation
  1286.181ms, median aggregate cache wait 16.791ms).
- Of those 13, four have aggregate cache wait less than 10ms;
  nine have JIT compilation at least 500ms.
- Median JIT compilation in the four high-stall/low-cache windows is
  several seconds. This points away from a **texture-lock-only**
  explanation for the biggest isolated frames.

The 5-second window ending at frame 3432 shows 23.322 FPS,
worst frame 312.942ms, 529.773ms multi-thread cache wait, and a
texture-cache lock maximum of 285.317592ms (two texture waits >10ms).
The next window, ending at frame 3547, shows a 980.574ms frame but
only 16.791ms cumulative cache wait. Other >900ms frames occur with
very low contention (e.g. frame 2420: worst 948.203ms, cache wait
0.439ms, JIT compilation 5620.873ms).

In a clean late window, ending at frame 33997, 150 frames in ~5s
are counted as exactly `v2=150` with a 60Hz display: effectively
one frame per two refresh intervals (~30 FPS). This demonstrates
regular two-vblank pacing but does not identify whether the guest
game, emulator scheduler, or presentation policy establishes that pace.

## How the measurements are defined

`jit_ms` tracks the development Dynarmic per-core **compilation**
timers (`eden_jit_compile`), not observed physical GPU load.
The numbers sum work across guest cores and cannot be subtracted
from frame duration. `cache_wait_ms` sums blocked CPU callback lock
waits across threads; it does not identify the owner holding the
mutex or the specific frame impacted.

The native Vulkan rasterizer does acquire the buffer/texture cache
pair in `PrepareDraw`, and the texture cache alone for multiple
operations. The sampled `pair_held` phase is 1/16 draws and does
not cover every other mutex owner or all off-draw critical sections.
At frame 3432, its observed max is 34.197us, insufficient to
identify who actually held the texture mutex for 285ms.

The measured GPU worker queue-idle fraction is **not** physical GPU
utilization. The frame count and `v2` presentation histogram do
not prove a hardware performance ceiling.

## Operational priority

1. **Root cause of JIT bursts:** inspect compiled-block counts, cache
   invalidations, per-core timing and repeat compilation in slow
   intervals. Prove which JIT work affects presentation progress.
2. **Texture-cache owner only for the rare 285ms tail:** identify
   the owner/critical section before changing lock scope/order;
   never remove fences or move guest writes outside protection.
3. **HUD/presentation freeze:** distinguish GPU command completion
   from final swap/presentation; frame stats above prove both normal
   and late intervals, not the cause of a persistent HUD stall.

## Scoped follow-up: per-present interval counter witness

`headless/present_interval_witness.h` is a native development-only,
opt-in observer. With detailed logging **and** `vulkan_frame_probe`
enabled, `GraphicsWindow::OnFrameDisplayed` reads existing 24
cumulative CPU/JIT/GPU counters once per displayed interval. It retains
only the widest **>=100 ms** interval in each five-second window.
`EDEN_PRESENT_INTERVAL_WITNESS` records the corresponding counter
deltas and prints `scope=between_presents`. No per-frame output,
guest-memory dereference, locks, allocations, clock probes inside the
witness, GPU reorder, or change to normal non-profile builds.

These are *overlapping worker counter deltas between two presentation
callbacks*, **not** a trace of the blocking work owned by one guest
frame. A high JIT delta and a delayed presentation remain correlation,
not proof that the JIT was holding the frame. An interval with no valid
monotonic counter pair produces no witness line.

A separate instrumentation gap matters: `jit_dups=on` only enables
`eden_jit_phases` duplicate accounting. Historically, the standard A64 compiler's development `EdenCompileTimer`
reported aggregate time without the phase/duplicate hook. Since the
20 October source change, default per-core A64 DEV now emits
`eden_jit_phases` only with detailed logging enabled, allowing phase
accumulation and opt-in `jit_dups` accounting without enabling shared
or batch JIT. The historical 15 October hardware logs did **not** have
this instrumentation; their zero duplicate values are still inconclusive.
The `EDEN_PERF_JITPATH` hook also belongs to the shared JIT, so its
zero `flush_all`/`flush_locations` values in that log are **not** a
measurement of invalidations in standard per-core Dynarmic. The native
`EDEN_FRAME_JIT_CORE.evacuations` counter separately covers automatic
whole-cache evacuations, **not** every per-location invalidation. Therefore
neither zero-valued duplicate/path counters nor zero evacuations prove that
the default JIT never recompiles. Do not enable shared/batch JIT merely
to repair these diagnostics.

### Offline consumption of interval witnesses

The existing `tools/analyze-fc27-stutter.py` analyzer now accepts
`EDEN_PRESENT_INTERVAL_WITNESS` records **only** when they have all
required counter fields, a matching preceding five-second
`EDEN_VULKAN_FRAME` report, a witness frame within that window, a
>=100-ms interval, and the literal `scope=between_presents`.
It retains the paired interval separately in `present_interval_witnesses`.
Older logs without this record return an empty list, **not** evidence
of zero JIT or GPU waits.

These are cumulative changes between two compositor callbacks, not
individual guest-frame execution timings. The analyzer never treats a
single observed gap as a proven stalled JIT, GPU fence, or game thread.

**Acceptance:** host evidence proves only counter pairing and opt-in
gating. Until a qualified native run is available, the cause of the
gameplay freeze, per-frame stalls, and physical GPU ownership is OPEN.

No native renderer/guest semantics are changed by this report.
The native post-store bridge #187 remains disabled. No console
build/release/game test is authorized by these observations.

`tools/analyze-ps5-cache-contention.py` now emits a deterministic
long-frame/JIT/lock classification with exact frame pairing.
`tools/check-fc27-cache-contention-classifier.py` exercises it
with synthetic records in host preflight. The original console
logs are private evidence, **not added to Git**.

## 20 octobre 2026 — Isolation du diagnostic JIT entre deux jeux

Le suivi facultatif `jit_dups=on` conservait son `unordered_map` de
localisations compilées dans une durée de vie statique commune à toutes les
sessions. Sur un autre jeu utilisant les mêmes adresses virtuelles, des
premières compilations pouvaient être classées comme doublons ; la mémoire
occupée par les anciennes entrées restait inutilement allouée.

`JitDuplicateHistory` détient désormais l'historique sous mutex, alloué
uniquement au premier enregistrement réel. Sa remise à zéro s'exécute à
la frontière de lancement, après arrêt des workers précédents, et réinitialise
les compteurs de doublons. Le suivi des compilations *dans* un même titre
reste identique ; les séries cumulatives de temps de compilation ne sont pas
remises à zéro par ce correctif. Le témoin C++ source réel vérifie ASan/UBSan,
plusieurs cœurs, sessions successives et sélection DEV.

Cette correction rend les prochaines captures `jit_dups` interprétables ;
elle ne prouve aucune baisse de frametime sur PS5.
