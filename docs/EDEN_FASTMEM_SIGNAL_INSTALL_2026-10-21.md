# Eden Encore — transactional signal installation and bounded fastmem JIT ranges

On the active A32 fastmem handler in `headless/fastmem_handler.cpp`, the former boolean short-circuit could successfully replace `SIGSEGV`, fail to replace `SIGBUS`, then return `installed=false` **with one handler still installed**. A subsequent unrelated fault could reach an unqualified custom trap path. The new installer restores the prior `SIGSEGV` action if the second registration fails and aborts when that restoration itself fails, rather than continuing in an ambiguous signal state.

`ValidCodeRange` also rejects null, reserved publication-sentinel, empty and wrapping JIT code spans **before** they are published into the lock-free fault lookup. The handler's signal-time range scan, callback and guest fallback semantics are unchanged; no locks or allocations were introduced into a signal handler.

The host test `tools/check-native-fastmem-signal-install-host.py` extracts the true initializer and range helper from maintained source, compiles them with C++20 ASan/UBSan and a deterministic `sigaction` mock, and verifies complete/partial-install rollback and boundary values. Fast gate and preflight execute it.

**422/491 inventoried sources reviewed; 7 remaining engine/runtime paths, 62 launcher UI sources separate.** No assertion of improved FC27 FPS, JIT throughput or console crash behavior.
