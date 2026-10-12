# R400 — PS5 VideoOut mode negotiation and multiresolution upstream audit (2026-10-13)

## Observed Encore bug and original PS5 Mesa comparison

Upstream [mihawk-99/PS5_Mesa 47e9eb61](https://github.com/mihawk-99/PS5_Mesa/commit/47e9eb61ee7e1112194557e1e047178562827bc6) (October 10, 2026) tested a PS5 driving a 1440p monitor: with console HDMI initially set to 1080p, `sceVideoOutIsOutputSupported(... HIGH_FRAME_RATE ...)` returned **0**; it returned **1** after setting the console to 1440p. With a supported mode, an actual successful `ConfigureOutput` call returned 0.

Our previous active WSI set `configured = supported` when `supported <= 0`, then `out->high_frame_rate = configured == 0`. Thus unsupported mode result 0 looked like configured 120Hz success and could enter 119.88Hz mode accounting without ever requesting it.

R400 fixes: `supported <= 0` sets configured=-1 and can never offer 119.88Hz; only supported>0 **and** configured==0 enable it. A failed 0ns vblank wait restores 59.94Hz. Encore already has a VRR-aware guard which does not mistake transient 48Hz vblanks for a stable 59.94Hz HDMI mode; keep it, don't blindly copy upstream's broader `period > limit` downgrade.

The fix is in the full active `vendor/encore-active/ps5-mesa/src/vulkan/wsi/wsi_common_videoout.c`, with pinned original untouched and the same change reproduced by `tools/patch-radv-wsi.py`. `tools/check-ps5-videoout-120hz-offer.py` checks mode offer, configure failure, zero vblank, stable 60Hz and VRR 48Hz cases. The existing byte-for-byte RADV/WSI source replay remains mandatory.

## Other WSI original improvement: selectable output sizes

Upstream [7b59ef27](https://github.com/mihawk-99/PS5_Mesa/commit/7b59ef27c1b09b9671bc4153c41940c3155c3af2) (October 4) added native VideoOut swapchain sizes 3840×2160, 2560×1440 and 1920×1080, with sets of five hardware buffers per size. Encore's pinned active WSI currently advertises only the 3840×2160 hardware mode, independently of the emulator's internal 1440p game-resolution setting.

**Defer** mass-merge: Encore has custom last-owner shutdown, physical memory and buffer-registration lifetime that must be reconciled with the upstream multi-set design; the upstream PS5 test reports a fourth 720p set refused by VideoOut. A poorly integrated replacement could break stable display and heap lifetime. Follow up separately with native-off source/host tests before replacing the swapchain model.

## Qualification and limits

R398 GitHub Actions [#38314780723](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38314780723) passed native compilation at `ab1ed98a`, **not** the newer R399/R400 sources. No new native compile or PS5 test is implied by this source-only update. FC27 severe perceived stutter at ~30fps, partial HUD/grass corruption and freezes require integrated live PS5 proof, not merely source regression passes.

## R400 combined native test request (after green source gate)

Source CI [#38318600041](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38318600041) finished **success** on 0c952eb938c2309f8eab2f8a099291b96ea6efba. The combined PS5 All-On diagnostic package should be built from a **single source commit** with `[full-build] [test-all-on]`, without publishing a release. The build's own complete native preflight must pass again and must record the binary/symbol/provenance SHA before requesting a console test.

It includes the previously integrated R396 AGC kick fix, R397/R398 official Mesa RADV backports, and post-R398 R399/R400 sampler and VideoOut changes. No visual/performance regression or freeze fix is proven until the actual PS5 binary is qualified. In particular, 120Hz negotiation correction only matters if a session requests 120Hz.

Upstream Eden [#4503](https://github.com/eden-emulator/mirror/commit/67bada77f8a4) suppresses shaders matching a known broken fragment pattern on non-NVIDIA Vulkan drivers. **Do not blindly import** that change for Encore's AMD-based PS5 while FC27 exhibits missing/flickering HUD and surface textures; first prove the exact shader pattern and demonstrate that skipping output is safe for this title.
