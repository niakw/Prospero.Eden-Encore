# Eden Encore — Maxwell local shader IR: constant-address fast path

**21 octobre 2026 — base `23f1bfffb`.**

The maintained Maxwell shader recompiler's `LoadLocal` validates the original byte offset against `LocalMemorySize - byte_advance`, avoiding an out-of-bounds load for both literal and dynamic addresses. Previously, even a compile-time **literal in range** proceeded through a dynamically emitted `ILessThan`, a safe-word `Select`, and a result `Select`.

After the existing early bounds rejection, such a literal now emits `v.ir.LoadLocal(word_offset)` immediately. It retains every bound check, never makes an out-of-bounds literal access, and leaves the dynamic path unchanged. This reduces needless IR for literal local loads; it does not change the GPU synchronization, shaders with dynamic offsets, or guest memory behavior.

`tools/check-ps5-shader-local-bounds-host.py` compiles extracted production helpers with clang ASan/UBSan. Added explicit observable IR comparison/selection counts: a valid immediate access must add no dynamic check/select, while a dynamic access must retain one comparison and two selections. Existing tests cover 32-bit address wrap, multiword tails, invalid static offsets, empty allocation and store-scratch preservation.

**Compte : 414/491 sources examinées, 15 fichiers moteur encore à examiner, 62 fichiers UI du lanceur séparés, 77 globalement.** No measured FPS or PS5 gameplay qualification claimed.
