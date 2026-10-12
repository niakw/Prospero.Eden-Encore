# R397 — Official Mesa/Khronos comparison outside PS5 forks (2026-10-12)

**Motivation:** FC27 0100C49025D3E000 / 1440p, 1x: visually severe stuttering despite 30 displayed FPS for much of the game, flickering/missing HUD and grass detail, with end-of-match game freeze (emulator still rendering). This investigation must keep both **visual correctness** and timing/liveness, not treat late50 counts as the whole problem.

## Verified versions / provenance

| Layer | Pinned in Encore | Public upstream | Integration constraints |
|---|---|---|---|
| Emulator | `vendor/sources/eden` pinned GitHub mirror `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`, backports and active Vulkan source in separate units | Eden emulator itself, **not Khronos/Vulkan** | Guest NVN textures, DMA, cache invalidation, host texture lifetime must be handled on emulator side |
| RADV driver + Mesa support libs | Full vendored `vendor/sources/ps5-mesa` **Mesa 26.2.0** from `mihawk-99/PS5_Mesa` at `0b2d6d1a61d9bbf89cf8beb88a696144f67c61f8` | Official Mesa 26.2.4, released **2026-10-01**, release notes: https://docs.mesa3d.org/relnotes/26.2.4.html | RADV targets Sony AGC via custom PS5 winsys/WSI; update generic units by surgical upstream changes only |
| Launcher OpenGL | `vendor/sources/opengl-mesa-26-2` = Mesa 26.2.0 official archive | Official Mesa 26.2.4 | Not the Vulkan in-game rendering backend; launcher isn't the observed FC27 match render path |
| Vulkan headers | `vendor/sources/opengl-vulkan-headers` pinned KhronosGroup/Vulkan-Headers `b51f6b865c18fc5b33990d12f75e8dfd672cede6` | KhronosGroup/Vulkan-Headers | Header/API registry updates do **not** include RADV runtime driver fixes or solve timing by themselves |
| PS5 glue | `vendor/encore-active/ps5-mesa` and Mihawk PS5_Vulkan SDK/build scripts | No official AGC PS5 release in standard Mesa | Must preserve Sony memory protection, flip/present queue and GPU wake semantics |

Official release history reviewed:
- https://docs.mesa3d.org/relnotes/26.2.1.html (2026-08-20)
- https://docs.mesa3d.org/relnotes/26.2.2.html (2026-09-02)
- https://docs.mesa3d.org/relnotes/26.2.3.html (2026-09-16)
- https://docs.mesa3d.org/relnotes/26.2.4.html (2026-10-01)

## Surgical backports actually implemented

### 1. Official Mesa 26.2.4: GFX10–11.7 bin-height bug

Source original: https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/1f4f4aeee9db552e2955db77ee5584aa729b0644

The pinned PS5 RADV computed:
```c
extent.width = MAX2(extent.width, 128);
extent.height = MAX2(extent.width, pdev->info.gfx_level >= GFX12 ? 128 : 64);
```
Mesa officially fixed second line to use `extent.height`, not already-clamped width. This affects bin rectangles on PS5's GFX10-class GPU, notably non-square render targets. Applied **exactly** in active `src/amd/vulkan/radv_cmd_buffer.c` and replayed from immutable base by `tools/patch-radv-wsi.py`. Host source-extracted ASan/UBSan regression: `tools/check-radv-mesa-2624-bin-height.py`. **May** improve GFX10 binning efficiency/correctness; user-perceived stutter and HUD artifacts are not yet proven fixed.

### 2. Official Mesa 26.2.2: texture array layer rounding

Source original: https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/3261364cab95877988e0bcf767e5f68c03f35652

The pinned `radv_pipeline.c` incorrectly gated the NIR array-layer rounding setting on *both* `conformant_trunc_coord` and `disable_trunc_coord`:
```c
.lower_array_layer_round_even =
    !compiler_info->ac->conformant_trunc_coord && !compiler_info->key.disable_trunc_coord,
```
Upstream corrected it to:
```c
.lower_array_layer_round_even = !compiler_info->ac->conformant_trunc_coord,
```
Affecting graphics texture array sampling semantics independent of optional TRUNC_COORD. Applied to a **sixth** complete active RADV translation unit `vendor/encore-active/ps5-mesa/src/amd/vulkan/radv_pipeline.c`, added to `tools/install-vendored-radv.py`, reproduced by the same pinned build oracle and required by `tools/check-vendored-radv-fork.py`. Host source-check/semantic ASan+UBSan regression: `tools/check-radv-mesa-2622-texture-array.py`. The immutable `vendor/sources/ps5-mesa` base is unchanged. **Candidate for real texture/grass/HUD correctness**, not proof until native FC27 test.

### 3. Official Mesa 26.2.2: guard indirect draws with zero count

Source: https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/a2f2518a9febf1b3b791cd2df079dbd25e56939b

Mesa found that AMD firmware can execute the first indirect draw even when the maximum draw count is zero. Backported the complete **shared** `radv_before_draw()` guard with explicit counts through ordinary direct, indirect, DGC, transform-feedback and multi-draw call sites. Encore's extra PS5 GS-compute raster caller additionally passes `direct ? 0 : 1` so the synthesized one-draw indirect packet is *not* spuriously suppressed. The deterministic port and pinned replay are in `tools/radv_official_indirect_draw_fix.py`, `tools/patch-radv-wsi.py`, and `tools/check-radv-official-indirect-draw.py`. This corrects a real GPU packet correctness issue, **not proof** of the FC27 freeze or all graphical anomalies.

### Previous PS5-specific RADV improvement retained

The R396 atomic AGC wake coalescing in `radv_ps5_platform.c` reduces redundant condition signals and protects concurrent submit accounting. It is not part of official Mesa and must remain PS5-specific. Tested by source-extracted parallel 12K DCBs in `tools/check-ps5-radv-kick-coalescing.py`.

## Other official commits inspected, *not blindly imported*

| Official upstream fix | Exact upstream | Audit decision |
|---|---|---|
| Skip zero-(max)drawCount indirect draws (firmware may execute phantom first draw) | https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/a2f2518a9febf1b3b791cd2df079dbd25e56939b | **Integrated with PS5 adaptation** in R397: the before-draw guard checks the guest-specified indirect count, while the custom GS-compute raster caller passes one for its single generated indirect packet. Exact source replay and host test `tools/check-radv-official-indirect-draw.py`; native behavior still unverified |
| sRGB compute color clears | https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/9a427b7668cfb19788c4347d7c3df01e10d9983b | Official fix for forced compute path or compute queue; lower FC27 priority unless matching clear path is observed |
| Depth/stencil resolve aspects | https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/6e18409d5800f975538236c4152fa4eeca3b444e | Integrated post-R398 in active meta resolve; source replay, not yet native rebuilt |
| Immutable sampler lifetimes with update templates | https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/7b5888e8ca77cc0b407c7fb113df85764b561a86 | Integrated R399 with two full active source units, template-owned copies, reproducible replay and ASan/UBSan; native runtime unverified |
| Broken rendering Persona 3 Reload on RDNA2 | https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/21e8be286d0e5888bee59243dc17a6159f613870 | Specific `RADV_FORCE_VRS` path; no evidence Encore enables it; do not treat as generic FC27 graphics cure |
| Official RADV/GFX11-12-compat features | Mesa 26.2.1–26.2.4 release notes | Exclude hardware-specific features that our GFX10-class PS5 cannot use. Sony WSI is PS5-specific |

## Implementation/validation discipline

1. **No global bump to Mesa 26.2.4**: C/C++ command buffer, shader compiler and AGC winsys form a coupled PS5 port. Instead preserve reproducible 26.2.0 input plus fully inspected, exact official patches in active source units.
2. `tools/check-vendored-radv-fork.py` must assert the entire active 10-file tree matches the replay oracle **byte-for-byte**, including PS5-specific earlier fixes.
3. Host tests run in source-only GitHub CI before any native build; they do not certify visual smoothness.
4. The R394 log user observation of visual stutter **at ~30 FPS** remains the primary quality criterion. Nominal present events do not measure game simulation step or correct texture contents. GPU buffer-cache contention explains only a subset of slow-frame periods; neither texture correctness nor guest freeze may be dismissed.
5. Rebuild RADV and final PS5 package from one unambiguous commit SHA only after source CI. Do not ask for repeated diagnostics until an integrated meaningful build is prepared.

## PS5 build provenance and outstanding native qualification

The R398 All-On PS5 build [#38314780723](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38314780723) **succeeded**, with verified archive structure and symbols, at SHA `ab1ed98a5cf170debd26959579b5676a602d704b`. That binary predates the official Mesa 26.2.4 depth/stencil clear/resolve backports and R399 sampler ownership source. It does **not** validate those later changes.

- Mesa original 26.2.0 inputs remain immutable. The production RADV installer now replaces 10 complete active files: the existing six, two meta clear/resolve files, and two descriptor template files. Every file must replay byte-for-byte from the pinned original and known exact transformations.
- Preflight #38316845719 failed only from this document's extra blank EOF line; the text-only fix is commit `f14f6f55`. Not a Vulkan failure.
- Before requesting another console run: pass the complete source/host CI, including R399 template-copy ASan/UBSan, then build **one explicit SHA** with native PS5 compiler and check artifact/symbol provenance.
- FC27 nominal 30fps with severe stutter, texture/HUD/grass loss and the gameplay freeze remain **unproven corrected** until measured on that binary.
