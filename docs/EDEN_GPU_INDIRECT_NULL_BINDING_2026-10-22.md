# Indirect Vulkan draw null binding guard — 22 October 2026

## Observed source path

The selected native `BufferCache::UpdateDrawIndirect` returns `NULL_BINDING`
when a guest indirect command byte span is empty, too large for u32,
or unmapped. The selected `BindHostDrawIndirectBuffers` previously
still touched/synchronized that sentinel and `RasterizerVulkan::DrawIndirect`
dereferenced the resulting sentinel buffer handle before recording
a `vkCmdDraw*Indirect` command. This could turn a rejected guest
command span into an invalid native draw.

## Correction and limits

- Skip null/zero byte bindings in the active cache sync path;
- Return a null pointer (and zero offset) from the active indirect command
  and count-buffer getters when the cache has no valid binding;
- Fail closed on either missing binding before `buffer->Handle()` and
  `scheduler.Record`. Normal valid draw submission is unchanged.
- Preserve guest cache mutex ownership, fence submission order, shader
  selection, texture invalidation, CPU/HLE scheduling and JIT parameters.

The selected source lives in `vendor/encore-active`; the pinned
backports remain untouched. Both independent R437 source reconstruction
oracles include this exact, audited transformation.

`tools/check-native-indirect-null-binding-host.py` compiles the extracted
native C++ cache getter/bind bodies at -O0 and -O2 under UBSan, verifies
zero and live bindings, and asserts that both Vulkan handle dereferences
are guarded. This is not PS5 validation, and does not prove FC27 contains
an unmapped indirect draw or that frame pacing/HUD issues are resolved.
