# R384 FC27 live PS5 FTP report — October 12 2026

R384 boot-trace and heap confirm commit fa2ad53c79f1f8039c29e60917491d671539e3f0. PS5 firmware 13.60. Read-only FTP snapshot copied privately to Mac /private/tmp/eden-r384-live-session; the game was still running at capture.

| Measurement | R370 full match/freeze | R384 ongoing session |
|---|---:|---:|
| Five-second windows | 240 | 135 |
| Mean FPS | 28.456 | 29.176 |
| >50ms frames/window | 4.417 | 1.985 |
| Worst frame | 2631ms | 626ms |
| Guest buffer lock wait/window | 39.76ms | 16.76ms |
| Buffer blocked calls/window | 2591 | 1403 |
| Sampled pair-held mean | 9.478us | 8.893us |
| Sampled pair-held max | 1024us | 1380us |
| R382 scheduler predispatches | uninstrumented | 432947 (3207/window) |
| GPU worker failed-pipeline draws | uninstrumented | 0 |

Caveat: match duration/scenes differ. Numeric reductions do not establish visually smooth gameplay; user reports persistent stutters and poor grass/texture/HUD detail.

New important evidence: R382 predispatch occurs about 22 times per displayed frame, far more frequently than expected for an exceptional chunk-capacity preflight. This may multiply Vulkan scheduler queue overhead while reducing lock waits. R386 investigation should quantify dispatch overhead and safely limit unnecessary predispatch, preserving FIFO ordering, guest cache coherency and fences. Do not infer that increasing FPS cap or removing locks is safe.

On PS5 firmware 13.60 BOTH kern.sched.topology_spec and kern.sched.ule.topology_spec return errno 2 (ENOENT). OS topology unavailable: 13 logical CPUs allowed, physical sibling assignment remains unproven. Never force fabricated SMT groups.

R381 GPU worker failed-pipeline draws: zero on the current session, so not a demonstrated graphics fix.

This is a mid-session snapshot, not final crash/freeze outcome.
