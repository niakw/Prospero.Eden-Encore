# Native texture descriptor guard — active source parity

During the October 21 review of missing jersey patches and intermittently
absent HUD textures, the **CMake-selected** maintained
`vendor/encore-active/eden-core/src/video_core/texture_cache/util.cpp`
still contained upstream's permissive `IsValidEntry`. The original R312 patch
corrected the pinned source in `vendor/sources`, but CMake explicitly removed
`texture_cache/util.cpp` and substituted the maintained ASTC utility TU.
That substitution discarded the R312 guard in the actual native binary.

The maintained TU now has the same PS5-specific decision semantics as R312:
reject texture format zero, reject non-sparse textures whose *first* GPU page
is not mapped even if the later-range overload finds another page, and preserve
the upstream host behavior and valid sparse textures. No GPU lock, fence,
barrier, texture mapping or pipeline timing is changed.

`tools/check-ps5-active-texture-descriptor-host.py` extracts the *actual*
`IsValidEntry` from the active file, compiles it in PS5 and host profiles
using memory-manager doubles, and checks valid/invalid/leading-missing/sparse
descriptors. The new check is in the fast gate and full source preflight, and
the original pinned-patch test checks active semantics too.

**Validation boundary:** the source and regression fix a proven *missing
native guard*. They do not yet prove FC27's specific HUD/jersey corruption is
caused by this case, nor that any stutters or frame pacing are corrected.
No PS5 console test or FPS result is claimed.

The sparse JIT selection remains untouched and not a fix for invalid
graphics descriptors. No shader pipeline or guest synchronization shortcut is
enabled.
