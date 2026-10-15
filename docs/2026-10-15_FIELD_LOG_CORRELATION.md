# 2026-10-15 — Field log analysis and stop-test checkpoint

Branch: **dev/ps5-sparse-jit**. Evidence from October 15 console logs, current code and an offline parser. **No runtime defect is claimed fixed. No new native package, release or console test is requested.**

## Tested binary identity

- Source SHA in the console trace: 5629395324ff65c98b50c44f35f2142a4a92654a.
- Firmware: 0x13600007; installed native title folder: PPSA99008.
- The newer branch HEAD and passing CI cannot retroactively change the tested binary.
- In-game configuration says title_override=1, own_mapping=0, profile map {}. The reported custom gameplay mapping is not shown as loaded.

## Controller/guest-input distinction

The raw PS5 sample is usable only when Data.connected is nonzero and its buttons do not carry kButtonIntercepted (third_party/ps5_pad.hpp). But the heartbeat 'connected=1' is an **open slot bitmap**, not Data.connected (headless/pad.cpp).

Across polls **273750–281250**, 7,500 more samples arrive in **30,914 ms**, without any rise in usable, intercepted, or read-error counters. With the sampled counter semantics, this is consistent with raw samples reporting disconnected. It is not proof of a guest CPU deadlock: system UI focus takeover near the end of the session is not ruled out.

After the plateau: options_edges=2, virtual published_plus_edges=2 and Npad LIFO reports two Plus edges. This shows input delivery through more than one layer, but **does not prove the title consumed those actions**. It also argues against a permanently missing physical Options-to-Npad route.

## GPU and memory

Replay of heap(20261015-161206).log and stderr(20261015-161213).log:

| Marker / observation | Result |
|---|---|
| Detailed pad heartbeats | 227 |
| Vulkan five-second windows | 232 |
| Windows below 20 FPS | 5 |
| Windows with worst individual frame >400 ms | 12 |
| Windows at 29.95–30.05 FPS | 190 |
| Mean of reported GPU idle milliseconds, final five windows | 3881.8 ms per window |
| Sparse JIT at core_destroyed | reserved=0 committed=0 |
| Heap pieces retained at core_destroyed | 1,744,830,464 bytes |
| Heap retention | 939,524,096 pinned + 805,306,368 unpinned, reclaim disabled because quiescence unproven |
| CPU topology | 13 claimed physical IDs, rejected; optimization skipped |
| Process CPU clock | valid=0 |

Important qualifiers:
- **Frames presented are not proof of changing guest game content.** Do not label a 30 FPS plateau as stable gameplay.
- GPU-idle values are instrumentation counters; no definitive hardware utilization or CPU bottleneck follows automatically.
- The retained heap is **not** a proven leak. Do not reclaim native pages without per-owner emptiness and quiescence proofs.
- GPU unmapping counters are zero within their measurement scope; this neither explains nor rules out all texture/HUD coherency faults.
- CPU topology and process-clock instrumentation are not verified on this firmware.

## Reproduce without touching the console

Run in a host terminal, with copies of the original logs stored outside the repo:

    python3 tools/analyze-ps5-session-log.py --self-test
    python3 tools/analyze-ps5-session-log.py --stderr 'stderr(20261015-161213).log' --heap 'heap(20261015-161206).log'

The synthetic self-test and replay of the user's supplied captures both ran locally. Raw user logs must not be committed to this public repository.

## Stop-test rules

1. Freeze console testing and do not publish another speculative experimental binary.
2. Only make risky runtime corrections after identifying an exact faulty path with source and reproducible evidence.
3. For a future source-only audit, prioritize guest-thread wait ownership/content progression and GPU buffer/texture freshness; treat heap lifetime independently.
4. Do not fix gameplay input by injecting synthetic HOME or Pause events; this trace does not warrant it.

Status: **forensic source analysis only; freeze/HUD/performance remain unsolved.**
