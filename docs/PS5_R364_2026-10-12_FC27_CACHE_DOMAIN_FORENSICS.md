# R364 — FC27 PS5 FTP log audit and per-cache guest wait attribution

## Real FTP evidence

Read-only FTP download through the authorized Mac, PS5 192.168.1.209 port 2121, directory /data/prosperoeden/logs/, on October 12. Local temporary copies live in /private/tmp/eden-r363-ftp-audit. Console log timestamps Oct 12 03:23–03:33 are BEFORE the new R363 build, so these logs do not measure R363.

- Earlier heap.prev.log: 210 approximately 5-second windows, 28.01 FPS average, 1,535 frames over 50 ms, no full producer GPU queue.
- Later heap.log: 115 approximately 5-second windows, 28.47 FPS average, 598 frames over 50 ms, 38 over 100 ms, no full producer GPU queue. Worker topology ready=0; no verified physical core allocation.
- Later session periods near 30 FPS: 79 windows, mean 1,250 guest cache lock collisions per 5s, 41.38 ms of cumulative guest waits per 5s, ~8.77 us per sampled draw holding GPU cache pair.
- Later session periods under 25 FPS: 17 windows, mean 8,488 collisions per 5s, 156.59 ms guest waiting per 5s, ~8.68 us per sampled draw holding GPU cache pair.
- Thus slow periods have ~6.8x as many collisions despite similar mean lock time per draw. These are time-window correlations, not causal proof and not a determination of the responsible cache.

## R364 diagnostic source changes

Only with detailed GPU logging enabled, GuestCacheLock now increments buffer versus texture domain counters on the same already-blocked paths. No cache lock is moved or eliminated, no GPU fence changes, and quiet-mode guest lock acquisitions still call the original mutex.lock immediately without sampling clocks or updating counters.

The five-second GPU snapshot adds EDEN_GUEST_CACHE_DOMAIN with domain=buffer|texture, cumulative and per-window contended, blocked, wait_ns. Texture covers CPU writes and GetFlushArea; buffer covers CPU writes. Concurrent counter snapshots may be slightly out of alignment: do not expect exact equality at every reporting instant.

Native generated Vulkan sources and pinned-source Python oracle must be byte identical. The R364 source-extracted host C++ fixture validates real GuestCacheLock code, separate buffer/texture blocking, overall totals, and zero clock work when diagnostics are quiet. Existing quiet GPU host regression remains in force.

No claim of performance improvement. Before another combined PS5 test, validate core CI and native PS5 build. Correlate per-domain blocked windows with late frames and GPU cache phases only after the new log format is present.
