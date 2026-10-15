# R1 — Offline forensic review, 15 October 2026 (no console test)

Branch: `dev/ps5-sparse-jit`. Evidence: user-provided `boot-trace(20261015-161205).txt`, `heap(20261015-161206).log`, `stderr(20261015-161213).log`, `result(1).tsv`, and prior logs. Examined build SHA: `5629395324ff65c98b50c44f35f2142a4a92654a`. This is **not** a new performance-fix claim. User has stopped console testing: do not request another run or publish another experimental build on the strength of these observations.

## Evidence, with limits

1. **Input availability, not a stopped poll worker.** In the current stderr, polls progress from 273750 to 281250 between epoch_ms 1792080623781 and 1792080654695 (about 30.9 s); `samples` rises from 730317 to 737817 while `usable` stays at 729588, `intercepted=0`, `errors=0`, and `last_read=1`. At 282500, `usable` resumes increasing. In `headless/pad.cpp::Poll`, `usable_samples` is incremented only for `ps5::pad::is_usable`; the predicate in `third_party/ps5_pad.hpp` requires `sample.connected != 0` and absence of the interception bit. Therefore the sampled controller records were non-usable, consistent with `sample.connected == 0` during that window. The heartbeat `connected=1` is **not** the sample's connected flag: it is the number/mask of opened controller slots. Do not diagnose this as a stopped thread or attribute it to a game deadlock. An OS focus/connection transition is possible but unproven.

2. **Rendering activity survives that interval.** Correlated `EDEN_TIME_ANCHOR` and `EDEN_VULKAN_FRAME` reports around epoch_ms 1792080623115–1792080658281 each report about 150 frames/5 s (30 FPS), `worst_ms` roughly 33–35 ms, and no `late50` or `gpu_full` events. The HID service command-206 cumulative count continues rising. This rules out a wholly stopped native render callback in that specific interval, but **does not prove image content changed or that the guest UI remained interactive**. GPU idle is about 3.6–3.9 s per 5 s window; this is not proof of a defective shader pipeline or an isolated GPU bottleneck.

3. **Measured launch spikes, not a sustained JIT bottleneck.** Early session reports `fps=21.562`, `worst_ms=894.738`, and `jit_ms=4243.201` in a multithreaded five-second profile. Later 30-FPS windows have near-zero JIT time, while the game can still appear frozen. A successful sparse JIT startup does not resolve the reported long-run symptoms.

4. **Memory retained, not proven leaked.** `core_destroyed` reports `live_bytes=6063474`, while native heap physical backing remains `1744830464` bytes (1664 MiB). `EDEN_HEAP_RETENTION` distinguishes 939524096 pinned and 805306368 unpinned bytes, both with `reclaim=disabled quiescence=unproven`. Do not infer that these pages are safe to unmap; see `docs/PS5_RESOURCE_RECLAIM_AND_GPU_CPU_SCALE_DESIGN.md`. A separate per-root accounting anomaly appears: `EDEN_HEAP_ROOT ... root=9 ... held_bytes=-6288 held_blocks=2`. A negative held byte count is invalid as a physical-memory measurement; audit the observational ledger and `realloc` ownership transitions before relying on root totals. Do **not** clamp this counter or reclaim based on it.

5. **CPU topology remains unverified.** `EDEN_PS5_CPU_TOPOLOGY_REJECT reason=more_than_8_physical_ids observed=13` and `EDEN_EXPERIMENT_CPU result=skipped reason=physical_topology_unverified`. The logical isolation optimization is not proved active; retaining the safety fallback is appropriate until a genuine kernel topology source validates the sibling groups.

6. **Texture/catalog path has a distinct defect.** `EDEN_CASE_RESULT` for `01007EF00011E000` is `front=1 back=1 spine=1` and the current launcher also logs texture creation; this proves resource preparation, **not** the exact final on-screen image. For `0100C49025D3E000`, the catalog lookup is `status=no-match` and `front=0 back=0 spine=0`: this is a confirmed catalog coverage gap, separate from frame stalls. Do not invent artwork associations.

7. **Cleanup did not crash in this run.** `result(1).tsv` marks `shortcut_return_to_menu`, `core_shutdown`, and `core_destroyed` as PASS. GPU unmapped counters are zero in captured summaries, though this does not rule out other texture/HUD synchronization problems.

## Engineering stop gate

- No new console request, default experimental toggles, release, runtime controller reconnect, physical unmap, JIT budget increase, or speculative frame-pacing change.
- Review-only candidates: (a) isolate actual guest image/UI progress from native present counts; (b) verify the semantics of disconnected controller samples and whether focus/system takeover explains them; (c) audit per-root memory ownership/counters without treating them as reclaim authorization; (d) correct only verified missing catalog mappings with a traceable source.
- A future gameplay patch must identify the source-level defect, include deterministic source/host regression coverage, and state which observed symptom it addresses. A green build and diagnostic-only changes are not grounds to request further console testing.

**Status:** forensic report committed to preserve evidence. No runtime patch or PS5 release, and no new console testing requested.
