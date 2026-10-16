# Guard dropped GS-as-compute draw pointers — 16 October 2026

The maintained RADV path could leave vertex-output, index, count and
output-index pointers equal to zero when GPU-side geometry setup rejected
an oversized draw. Later passes risked dereferencing null GPU addresses.

Now the CPU-side parameters default to a dedicated 256-byte sink, and the
rejected GPU-side setup assigns its three outputs to the draw's read-only
sink. Both source units are versioned, with pinned Mesa left immutable.

Native build input lists, source-equivalence oracle and cached-driver
fingerprint include the maintained OpenCL source, now 12 files. Clang
ASan/UBSan host test extracts the actual rejected-draw code and compares
old null pointers to the guarded branch. No native driver was compiled.

This does not establish that the known game freezes/HUD issues reached
this specific geometry-shader path, or that console performance improved.
Reference: https://github.com/blackbearreloaded/ProsperoEden/commit/80bfd2b67f81
