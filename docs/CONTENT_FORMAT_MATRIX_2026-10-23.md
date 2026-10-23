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
| `.nro` | Homebrew program | **Selectable**, may not be a full game | Upstream NRO |
| `.nso` | Executable module | **Selectable**, may require other program contents | Upstream NSO, retaining LZ4 and ZBIC/zstd |
| `.nca` | Content archive | **Selectable**, only bootable when complete/valid | Upstream NCA |
| `.nax`, `.kip` | Program/archive types | **Selectable**, not always bootable alone | Upstream NAX and KIP loaders |
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

`headless/CMakeLists.txt` selects those five maintained source owners and compiles the NCZ adapter; it does not generate C++ by textual substitutions. Pinned Eden sources remain unchanged. Library filename checks are case-insensitive for all **nine** picker extensions.

## Storage, memory and access model

- NCZ **block** compression: bounded decompressed blocks kept in memory; no full copy required.
- NCZ **solid** compression: during play, a decompressed copy can be written under `/data/prosperoeden/user/cache/nsz/`. Outside a game, limited, checksummed reading windows are kept instead.
- Temporary `.part` files are created exclusively and cache opens refuse symlinks. The launcher refuses symlinked cache directory components. Unsafe archive entry names are rejected.
- Touchpad + L1 during loading stops permitting further solid unpack; the runtime closes its session-wide permission on exit.
- Insufficient storage may cause a slow sequential-read fallback; there is no promise of interactive performance from that path.

## Evidence and remaining acceptance

- **Source comparison:** the five maintained owners have been compared with their pinned baselines; each contains its reviewed NCZ adaptation, plus `ncz_vfs.h` inclusion where used. The maintained `loader.cpp` additionally includes the explicitly reviewed NAX extension fallback.
- **Committed host checks:** `tools/check-ncz.py` runs synthetic block/solid NCZ reconstruction under ASan/UBSan; `tools/check-encore-ncz-sources.py` verifies native-owner selection, all nine picker extensions in upper/lowercase, storage counts, and safe direct-loader metadata routing.
- **Security regression:** `headless/ncz_check.cpp` exercises symlinked cache paths and verifies they cannot overwrite a protected file.
- **Unverified:** full host CI and native PS5 package at the current HEAD; no console gameplay test of NSZ/XCZ.
- **FC27:** engine exits F01–F06 remain open; this feature does not constitute a fix for stutter, missing textures or the in-game HUD. Console qualification F07 remains postponed until the engine is ready.

This document is an implementation/validation ledger, not a compatibility claim for released binaries.


## October 23 integration checkpoint

- Selected maintained code is byte-for-byte equal to the five pinned Eden
  sources after the five reviewed NCZ transformations, with only the required
  VFS include on the two affected source owners.
- The launcher now enables solid unpack **before content/update registration**,
  avoids enabling it for ordinary Library discovery, and turns it off during
  game cancellation/teardown.
- NCZ cache protection rejects path separators, embedded NULs, symlinked
  cache directories, symlinked cache files and pre-existing partial files.
- A locally compiled **isolated reproduction** of the actual
  `headless/game_files.h` code passes the initial four-container extension cases and
  nine rejected examples; the maintained CI oracle now covers all nine loader extensions under `-O0` and `-O2` with UBSan.
- An isolated source-extracted NCZ cache open guard rejects symlinked
  `.unpacked`, `.part` and `.pieces` files under `-O0`/`-O2` with
  UBSan. The full `headless/ncz_check.cpp` suite is checked into the host CI.
- **Still not independently verified:** complete `check-ncz.py` execution
  on the current repository tree, CMake-generated native target linkage, full
  PlayStation 5 native package and NSZ/XCZ game runtime.
- This checkpoint explicitly requests the native CI build using the commit
  marker `[full-build]`; a CI trigger does not itself mean the job passed.


## All-format Library routing — 23 October

The Encore game picker and its storage counter now accept these **nine**
case-insensitive extensions: `.nsp`, `.xci`, `.nsz`, `.xcz`, `.nro`,
`.nso`, `.nca`, `.nax`, `.kip`. Each is passed to the matching native
Eden loader; for raw executable/archive types the Library uses filename or
ID fallback rather than incorrectly opening them as NSP/XCI Control RomFS.
`.nax` now also has an explicit filename-type fallback, while signature
identification still takes precedence.

The underlying loader additionally identifies an extracted-game `main`
with its associated directory content, and special NAX-style `00`
inputs; these are **layout-specific paths**, not ordinary extensions
discovered by the TV Library. There is no independent game loader for
raw `.ncz`, `.zst`, `.zbic` or `.lz4` files.

**Compression remains separate:** the original LZ4 NSO segment path and
Encore's ZBIC/zstd segment path are retained, alongside the NCZ zstd
block/solid reader for NSZ/XCZ. An executable/archive may be recognized
but fail to boot when it lacks its companion files or required metadata.
No blanket compatibility claim is made before native CI and hardware tests.


## Final all-extension source checkpoint

The TV Library's **actual scanning loop**, not just `ValidRomFilename`,
now checks `Eden::IsGameFile(file)` from `headless/game_files.h` rather
than the historical NSP/XCI-only conditional. This unifies discovery,
saved/recents selection, development-ROM filtering and storage counts
for the nine file extensions.

The generic Metadata Bridge recognizes the distinction between full
NSP/XCI-style containers and direct NRO/NSO/NCA/NAX/KIP files. Direct
modules are never misparsed as submission packages for icon/language
extraction. The native core makes the final decision about bootability.

A recheck of **all five** NCZ-aware maintained source owners against the
pinned Eden files confirmed byte-for-byte expected transformations,
including the explicit NAX filename fallback. `check-encore-ncz-sources.py`
contains a negative assertion that the legacy
`format != "NSP" && format != "XCI"` scan condition cannot return.
The source and host-test gate is committed, but the native build status
for the latest HEAD remains unknown; these are **development** features,
not a hardware-tested compatibility statement.

The pre-existing FC27 performance and memory-correctness work remains
separate. F01-F06 cannot be closed merely because more loading formats
are visible in the front-end. A complete native compilation is requested
with `[full-build]`, and F07 still requires the planned final PS5
qualification, not an immediate test.
