# Shader local scratch bounds — 16 October 2026

The pinned shader translator selects zero for an out-of-bounds local read,
but emits `ir.LoadLocal(word_offset)` before selecting the result. In shader
IR this is an actual read operation, not a conditional expression; the
invalid scratch index can reach the GPU. Local writes from dynamic offsets
are unguarded, including the tail of multiword stores.

The maintained, native-only shader source first selects a valid local address
then performs reads, returns zero for out-of-bounds reads, and preserves the
previous contents of word zero when an invalid dynamic store is emitted.
Immediate out-of-bounds tail words are dropped, and zero-sized scratch
allocation never emits a read or write. The original pinned source remains
unchanged. The shader_recompiler target uses the maintained single TU.

The CI host regression compiles the real pinned and maintained helper code
with Clang ASan/UBSan and a bounded scratch-memory mock. The pinned helper
must reproduce the unsafe load; the maintained helper must handle dynamic
and immediate OOB access without touching invalid scratch. Source guards
ensure 8/16/32/64/128 bit stores route through the checked helper.

This is a source-level correctness improvement, not evidence that past FC27
crashes or HUD defects had this cause; it does not qualify a console build.
Reference: https://github.com/blackbearreloaded/ProsperoEden/commit/a302cde87a03158bfeab2a37aaf27e772d184b9d
