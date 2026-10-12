# R393: per-guest-thread IPC wait attribution for FC27

The R384 freeze still renders near 30 FPS while the guest appears to repeat an unchanging workload. Older counters aggregated all svcSendSyncRequest wait time, masking the identity of the guest thread actually waiting. R393 selectively adapts ProsperoEden upstream 6cab7898c05d: https://github.com/blackbearreloaded/ProsperoEden/commit/6cab7898c05d

## Design

Only compiled in the development-profile derived svc_ipc.cpp, and only executed with Detailed Logging ON: read thread ID and wall-clock before SendSyncRequest, record return duration and ID in one function, then return original IPC result unchanged.

128 fixed atomic slots, open addressing and explicit overflow. Four cumulative duration bins: under 50us, 50-500us, 500us-5ms and >=5ms. Up to 12 heaviest thread records printed in the existing five-second GPU snapshot as EDEN_DEV_IPC_THREAD with tid, calls, ns, max_ns; EDEN_DEV_IPCHIST follows. No guest-memory name lookup, heap growth, lock acquisition or per-call printing, and no added quiet-gameplay instrumentation.

Do NOT interpret a large cumulative wait as proof of a current deadlock. Capturing currently blocked thread state and correlating JIT PC samples requires further instrumentation. The upstream wake-to-run scheduler probe b59cef86fd85 deliberately remains excluded: it takes more clocks in scheduler critical sections and could obscure existing FC27 performance issues.

## Source validation

tools/check-ps5-guest-ipc-thread-profile.py compiles the EXACT helper body from production header with ASan/UBSan and concurrent colliding thread IDs, validates aggregate single-counting, 128-slot capacity, overflow, latency histogram and worst IPC duration. It also verifies CMake source replacement captures thread ID before the blocking call and five-second reporter bounds.

Both CI preflight workflows now include this test. No PS5 build or console test was performed for R393.
