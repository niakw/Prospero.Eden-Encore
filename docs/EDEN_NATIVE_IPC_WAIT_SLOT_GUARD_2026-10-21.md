# Eden Encore — safe IPC wait result index in production

`vendor/encore-active/eden-core/src/core/hle/kernel/svc/svc_ipc_standard.cpp` uses `KSynchronizationObject::Wait` to select a server session to receive from. Successful waits previously dereferenced `objs[index]` directly, trusting the reported slot. If a native synchronization bug or corrupted wake result produced a negative, out-of-range, or null entry, this dereference could fault.

The shipping source now checks `index < 0 || index >= num_objects || objs[index] == nullptr` **only when Wait reports success**. Invalid successes set `*out_index=-1` and return `ResultOutOfRange`, rather than touching invalid memory. Valid-success, cancellation, termination, timeout output semantics, and `ResultNotFound` retries are unchanged. The DEV-profile IPC source is deliberately untouched.

`tools/verify/hle/check-native-hle-ipc-timeout-host.py` still requires exact pinned-source parity plus three authorized transformations. `check-native-hle-ipc-receive-index-host.py` runs the real loop under ASan/UBSan for both standard/DEV, and tests malformed success indices and null session objects for standard. Both are in the fast gate and preflight.

**424/491 sources accounted for; 5 engine/runtime files remain plus 62 launcher UI files.** No console FPS/deadlock clearance is claimed: this is failure containment of an impossible-success condition.
