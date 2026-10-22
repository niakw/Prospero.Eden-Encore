# GPU indirect draw byte-range guard — 22 October 2026

## Confirmed source issue

The maintained BufferCache::UpdateDrawIndirect in
`vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h`
passed a `size_t` indirect-command length through `static_cast<u32>(size)`
twice without checking that the span was nonempty and representable.
A 4 GiB input could become a zero-byte `FindBuffer` request; an input
slightly larger could silently bind an incorrectly short command buffer.

## Correction

Reject zero-length and greater-than-u32 ranges before address translation,
resetting the binding to `NULL_BINDING`. Keep valid 1..UINT32_MAX spans,
the count-buffer path, the existing address translation failure handling,
buffer caching, and the draw submission order unchanged. The pinned
upstream backport is not altered. The maintained-source replay oracles
in `tools/check-ps5-buffer-pages-r437.py` and
`tools/check-vendor-consolidation-debt.py` include this exact delta.

## Verification

`tools/check-native-indirect-draw-range-host.py` extracts the selected
C++ method and compiles it at -O0 and -O2 with UBSan. Cases include a
normal count/indirect pair, zero size, 4 GiB overflow, UINT32_MAX,
unmapped memory and SIZE_MAX. The host test is included in fast gate
and full preflight. CI and a PS5-native build must qualify this commit
separately; no gameplay, FPS or HUD correction is claimed.
