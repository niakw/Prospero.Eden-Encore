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

## R400 native preparation failure and deterministic cache migration

Initial combined R400 All-On workflow [#38319048610](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38319048610) passed source, SDK and release gates, then failed in `make prepare` at `install-vendored-radv.py`. Cached PS5 RADV `wsi_common_videoout.c` had SHA256 `6d54b8d68cc383faa9bbd910e327824689b5315e7ee5617d8981f582c47c2eaa`, which was not equal to either immutable PS5 Mesa upstream or new R400 active WSI.

**Provenance established:** that SHA256 is the exact, complete Encore WSI source at R398 commit `ab1ed98a5cf170debd26959579b5676a602d704b` (Git blob `6e77c7e40de7158fe46774221934622c9411fbd7`), also unchanged at later pre-R400 commits `5fb6aa6c` and `b7528d7f`. It is expected in the native build cache.

The updated installer permits **only this pinned historical SHA256** for the WSI path in addition to the original/up-to-date source, then atomically replaces it with the current canonical active file and invalidates native provenance. Unrecognized bytes for this or any other RADV path remain rejected. `tools/fixtures/ps5-r398-wsi-videoout.c` preserves the full old source, and `tools/check-vendored-radv-fork.py` verifies the real old-to-new staged replacement plus refusal on unknown inputs.

This is a reproducible build-cache migration, **not** a change to game-rendering logic and not evidence of a native R400 package yet.

## R400b native rebuild after deterministic WSI migration

Source CI [#38319934068](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38319934068) passed at `35faea74bd9117fa343438c693c301298b76cdc9`. This commit launches a combined All-On PS5 build using `[full-build] [test-all-on]`; it contains no runtime code changes relative to the green source SHA. Verify the exact resulting build SHA, source checks, RADV install, binary, symbol provenance and distributable artifact before requesting any live FC27 test. Do not publish a release.

## R400c: enumerate all historical compiler inputs, not just one failing path

A second native attempt [#38320275017](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38320275017) correctly passed the prior WSI cache migration, but failed on stale `radv_ps5_platform.c` SHA256 `8112c2b41a600043d3096a0198c4e3c2d7dcf6b56e8f738f6ce8eb537943725c`. GitHub source history identifies that exact source as `1c874ff951b02cf6ea8cef7ce4b110258727575c` (R343), before the R396 concurrent-submission accounting and coalesced wakeups.

Instead of authorizing only this one file, a full audit compared the **10 RADV production-owned input paths** against R343's active fork. Five paths had R343 historical active snapshots; the other five were not yet modified/added in that fork and are handled by the immutable original Mesa pinned source rule. All five verified historical files are checked in under `tools/fixtures` with their original Git blob bytes (the WSI fixture remains named R398 because its exact bytes were unchanged since R343).

| File | Authenticated cached R343 SHA256 prefix |
| --- | --- |
| `wsi_common_videoout.c` | `6d54b8d68cc3` |
| `radv_cmd_buffer.c` | `27e495385388` |
| `radv_physical_device.c` | `56aed8905eea` |
| `radv_ps5_winsys.c` | `0aa478ae4c4d` |
| `radv_ps5_platform.c` | `8112c2b41a60` |

The installer authorizes these **path-bound historical hashes only**, plus the pinned Mesa originals and exact current active files. It never bypasses verification for unknown bytes. The deterministic host regression now stages **all five old files at once**, upgrades to the canonical ten-file fork, checks the second install changes nothing, and refuses unknown modifications. This avoids a one-file-at-a-time build-and-fail loop and preserves source/compiled code provenance.

No FC27 performance, HUD or freeze improvement is implied by this cache migration. R400c needs source CI and a single full native All-On build at a known SHA.
