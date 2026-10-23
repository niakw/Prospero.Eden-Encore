# Encore — game containers, internal compression and validation

**Branch:** `dev/ps5-sparse-jit`. **Source of NSZ/XCZ reader:** [community contribution #285](https://github.com/Swordpdf/ProsperoEden/pull/285), adapted to Encore's complete-source architecture.

## Format support matrix

| Input | Type | Recognized by current Library? | Internal loader |
| --- | --- | --- | --- |
| `.nsp` | Game/update/DLC container | Yes | NSP |
| `.xci` | Cartridge game container | Yes | XCI |
| `.nsz` | NSP with compressed NCAs | Experimental | NSP + NCZ VFS |
| `.xcz` | XCI with compressed NCAs | Experimental | XCI + NCZ VFS |
| `.ncz` | Compressed NCA inside NSZ/XCZ | No | Translated to `.nca` by NCZ adapter |
| `.nro` | Homebrew program | No, not a standard Encore game-library entry | Upstream NRO |
| `.nso` | Executable module | No | Upstream NSO, including retained LZ4 and ZBIC/zstd |
| `.nca` | Content archive | No | Upstream NCA |
| NAX, KIP | Internal program/archive types | No | Upstream loaders (NAX identification / KIP) |
| Deconstructed game folder | Extracted content | No, not in the ordinary Library scan | Upstream deconstructed-directory loader |
| `.zst`, `.zstd`, `.zbic` | Compression-oriented extensions | **No** | **Not** independent game containers |

**Do not conflate file formats:** zstd is used by the NCZ decompressor and the separately retained ZBIC path. LZ4 remains supported for NSO segments. This does **not** mean a raw `.zst` or `.zbic` is a playable title.

## Native source ownership

The reader and front-end adapter are `headless/ncz.h`, `headless/ncz.cpp`, `headless/ncz_vfs.h`. Five complete adapted translation units live under `vendor/encore-active/eden-core/src/core/`:

- `file_sys/submission_package.cpp` — resolve embedded `.ncz` when `.nca` is absent
- `file_sys/card_image.cpp` — open NCZ members as NCA views
- `loader/loader.cpp` — route NSZ to NSP and XCZ to XCI
- `loader/nsp.cpp` — accept NCZ member names during container identification
- `file_sys/registered_cache.cpp` — include compressed update/DLC containers

`headless/CMakeLists.txt` selects those five maintained source owners and compiles the NCZ adapter; it does not generate C++ by textual substitutions. Pinned Eden sources remain unchanged. Library filename checks are case-insensitive for the four extensions.

## Storage, memory and access model

- NCZ **block** compression: bounded decompressed blocks kept in memory; no full copy required.
- NCZ **solid** compression: during play, a decompressed copy can be written under `/data/prosperoeden/user/cache/nsz/`. Outside a game, limited, checksummed reading windows are kept instead.
- Temporary `.part` files are created exclusively and cache opens refuse symlinks. The launcher refuses symlinked cache directory components. Unsafe archive entry names are rejected.
- Touchpad + L1 during loading stops permitting further solid unpack; the runtime closes its session-wide permission on exit.
- Insufficient storage may cause a slow sequential-read fallback; there is no promise of interactive performance from that path.

## Evidence and remaining acceptance

- **Source comparison:** the five maintained owners have been compared with their pinned baselines; each contains only its expected NCZ adaptation, plus `ncz_vfs.h` inclusion where used.
- **Committed host checks:** `tools/check-ncz.py` runs synthetic block/solid NCZ reconstruction under ASan/UBSan; `tools/check-encore-ncz-sources.py` verifies native-owner selection and all eight case variants of the four accepted Library extensions.
- **Security regression:** `headless/ncz_check.cpp` exercises symlinked cache paths and verifies they cannot overwrite a protected file.
- **Unverified:** full host CI and native PS5 package at the current HEAD; no console gameplay test of NSZ/XCZ.
- **FC27:** engine exits F01–F06 remain open; this feature does not constitute a fix for stutter, missing textures or the in-game HUD. Console qualification F07 remains postponed until the engine is ready.

This document is an implementation/validation ledger, not a compatibility claim for released binaries.
