# Native guest RAM range endpoint overflow guard — 2026-10-17

Pinned source: `src/core/memory.cpp`, `Memory::IsValidVirtualAddressRange(base, size)`.

The source computes `end = base + size` and then iterates page indices while
`page < end`. For base close to `UINT64_MAX` and a nonzero size that wraps,
end becomes smaller than the aligned beginning, so the loop executes **zero
times and returns true** for an invalid address range. This is a concrete
unsigned arithmetic correctness defect in the source, not an established cause
of FC27 freezes.

The active **native-derived** memory translation unit (`memory-ps5.cpp`)
now includes a fail-closed CMake transform requiring the unique pinned source
anchor. It rejects `size > UINT64_MAX - GetInteger(base)` before the addition.
The host-only regression compiles the unchanged pinned C++ method and the
same method transformed by **executing the CMake helper**; the original
incorrectly accepts a wrapped range and the derived version rejects it.
Ordinary mapped and unmapped ranges preserve their behavior.

No vendored source file or public interface changed, no GPU/JIT waits were
altered, no native console build or game test was performed and #187 remains
disabled. Do not interpret a green host check as a gameplay fix.
