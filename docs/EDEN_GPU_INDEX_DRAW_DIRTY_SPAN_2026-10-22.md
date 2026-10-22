# Indexed draw command range and cache dirty flag — 22 October 2026

## Cause

The pinned `engines/draw_manager.cpp` receives dynamic index `first` /
`count` from macro and indirect draw calls, independently of the
underlying Maxwell register writes. `BufferCache::UpdateIndexBuffer` skips
rebinding when `Dirty::IndexBuffer` is false. Thus, consecutive macro
draws with different index ranges but the same register values could
reuse the preceding draw's buffer binding extent.

The old draw-manager already forced dirty for index-small and inline
index draws; `DrawIndex`, `DrawIndexedIndirect`, and indexed
`DrawEnd` returning from a macro draw omitted that transition.

## Maintained fix

- Native CMake selects the complete maintained TU at
  `vendor/encore-active/eden-core/src/video_core/engines/draw_manager.cpp`,
  removing the pinned `engines/draw_manager.cpp` from the video_core target.
- Those three methods now arm `Dirty::IndexBuffer` **only when first/count
  changes**. Existing dirty state is never cleared here.
- Identical ranges retain the existing no-op cache fast path. Index-small,
  inline indices, nonindexed draws, shader selection, cache locks,
  Vulkan commands, and JIT policy remain unmodified.

## Proof / qualification

`tools/check-native-index-draw-dirty-span-host.py` enforces whole-file parity
except for the three selected methods, compiles the real extracted C++
methods at O0/O2 with UBSan, and checks changed/same indexed spans,
indexed indirect draws, return to general register state, previously set
dirty flags and inline-index forced refresh.

Fast gate and full source preflight invoke this regression. A green native
PS5 build at the new commit is also required. No assertion is made
that this particular missed index update occurred in FC27, or that it
eliminates GPU contention, stutters, missing HUD or jersey textures.
