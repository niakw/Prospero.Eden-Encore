# GPU sync fence publication — 16 October 2026

The pinned native GPU implementation increments `last_sync_fence` before
`sync_requests.emplace_back`. If the callback insertion throws, a fence
number is consumed without creating an executable callback. A subsequent
CPU waiter could therefore wait for a fence the worker cannot acknowledge.

The native-only CMake source derivation now inserts the callback **before**
incrementing the fence counter, under the same mutex. A deterministic Clang
ASan/UBSan regression compiles the generated request and tick methods,
injects a callback copy throwing `std::bad_alloc`, and verifies that the
next successful callback receives and completes fence 1.

This is source-level correctness, **not evidence** that FC27 freezes were
caused by callback allocation failure. No console build, release or device
test is requested.
