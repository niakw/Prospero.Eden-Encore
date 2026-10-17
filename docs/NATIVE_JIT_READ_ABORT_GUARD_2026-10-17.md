# Guard guest RAM reads after Dynarmic abort checks — 2026-10-17

The pinned `DynarmicCallbacks32` and `DynarmicCallbacks64` scalar read
callbacks invoke `CheckMemoryAccess` but **ignore its false return** and
continue into `m_memory.Read8/16/32/64`. A64 `MemoryRead128` reads twice.
A failed check already requests `HaltExecution(PrefetchAbort/DataAbort)`,
while the write callbacks correctly skip forbidden accesses.

The native-only derivative now short-circuits all **nine** read callbacks
(four A32, five A64), returning zero/zero-vector after a denied access.
Successful reads follow the original method bodies, unchanged. The helper
fails source derivation if any pinned callback signature changes. The guest
CPU interface, JIT allocator and code-cache semantics are untouched.
Disabled experimental bridge #187 remains off.

`tools/check-native-jit-memory-read-guard-host.py` executes the CMake
derivation on the actual pinned callbacks and compiles their bodies against
mock memory. It separately verifies both ISAs with accepted and denied
accesses; original methods are negative controls. No native device build,
game-performance claim or evidence of FC27 root-cause resolution.
