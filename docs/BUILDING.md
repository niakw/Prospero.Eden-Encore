# Building Prospero.Eden Encore

The authoritative release build runs on **Ubuntu 24.04**. WSL/Linux hosts with the same tools are suitable.
Encore also supports local native-build iteration on Apple Silicon macOS through `tools/host-env.sh` and Homebrew LLVM 18; CI remains the release authority.

```bash
make release
```

The first build fetches pinned dependencies, prepares RADV and builds Eden for PS5. Later builds reuse
the dependency cache, the checkout-specific native build cache and ccache.

## Release outputs

A successful `make release` writes:

- `dist/Prospero.Eden-Encore-R1.zip` — standard installation bundle;
- `dist/Prospero.Eden-Encore-R1.ffpfsc` — optional ShadowMountPlus PFS image;
- `dist/SHA256SUMS` — SHA-256 digests for both distributable binaries;
- `dist/release-notes.md` — extracted from the matching README `Changes in Encore R1` section.

The ZIP includes the `PPSA99008` application folder plus README, INSTALL, SECURITY, LICENSE and
third-party notices.

Unstripped symbols are kept separately under:

```text
build/symbols/Prospero.Eden-Encore-R1.elf
```

They are uploaded as a CI artifact for crash diagnosis but are not attached to the public Release.

## Make targets

| Target | What it does |
| --- | --- |
| `make` / `make release` | Full release bundle |
| `make package` | App folder only: `build/release/PPSA99008` |
| `make image` | FFPFSC image only |
| `make install PS5_HOST=<address>` | Copy the built app folder over FTP |
| `make dev DEV_TITLE=<title ID>` | Development build with profiling/dev switches |
| `make test` | Host emulator/tests |
| `make deps` | Fetch missing pinned dependencies |
| `make deps-status` | Show dependency locations and pin state |
| `make prepare` | Prepare dependencies/tooling/driver inputs without the final Eden build |
| `make toolchain` | Validate required host tools |
| `make clean` | Remove `build/` and `dist/` |
| `make distclean` | Also remove fetched local dependencies/build cache |

`JOBS=<n>` controls native compile parallelism.

## Dependencies

Primary source/build inputs are pinned in `tools/deps.json`. Archives are hash-checked and Git
repositories are fetched at explicit commits. The dependency cache defaults to:

```text
~/.cache/prosperoeden-deps
```

Important inputs include:

- **Eden** at the revision pinned by Encore;
- Eden's pinned FFmpeg source;
- PS5 OpenGL source snapshot `ad2807d` (the SDK is rebuilt and manifest-verified by `tools/build-opengl-sdk.sh`);
- PacBrew OpenSSL/zlib inputs;
- LLVM compiler-rt and fmt inputs;
- **ps5-native-app-boilerplate** / PS5 Payload SDK;
- Mihawk PS5 Vulkan/Mesa/Payload SDK sources used for RADV.

RADV is isolated and validated before use. Encore's WSI adaptation is checked by
`tools/patch-radv-wsi.py`.

The OpenGL build deliberately does **not** consume a moving upstream HEAD or an unverified local
archive. `tools/deps.json` pins `blackbearreloaded/ps5-opengl` to `ad2807d`; `make prepare` builds
`.local/ps5-opengl-sdk-ad2807d`, verifies every entry in its `manifest.sha256`, and writes the exact
source commit beside it. Release validation records the resulting manifest and all SDK files in the
candidate receipt.

The optional FFPFSC step fetches **PSBrew/MkPFS** at the immutable commit recorded in
`tools/ci/package-image.sh` and caches it under `~/.cache/prosperoeden-mkpfs`.

## Fast preflight vs native compile

The release build intentionally runs source/harness checks **before** the expensive native compile
whenever those checks only need the configured/generated source tree. This catches stale extraction
harnesses and source-shape regressions early.

After CMake configuration, preflight includes checks for:

- slab lifetime and audio shutdown;
- load-failure recovery;
- ProsperoEden legacy migration;
- NSO memory / ZBIC behavior;
- performance/startup/worker/TSC contracts;
- JIT protection/allocation/patch/assert paths;
- crash reporting;
- native GPU queue/thread/producer/sync behavior;
- NVDRV process lifetime;
- integer buffer clear;
- game-capture shutdown;
- HUD/frame summary behavior.

Only checks that need compiled dependency records or machine code remain after the native build,
notably the sparse-header dependency check and native exclusive-monitor assembly validation.

## Launcher

The launcher lives under `headless/prosperoeden`. Catalog/font/sound assets are copied from the committed UI tree; release packaging generates `brand.tga` from the canonical Encore logo and `backdrop.tga` from the canonical Encore background.

Useful tooling under `tools/launcher` includes:

- `assets.sh` — font/art generation;
- `process-sfx.py` — sound preparation;
- `bake-wordmark.py` — loading wordmark;
- `preview.sh` — host UI previews;
- `strings.py` — extraction/catalog validation;
- `text-check.sh` — text/RTL validation.

The release workflow runs `python3 -B tools/launcher/strings.py check` before native compilation.

## Host toolchain

`make toolchain` checks the required toolset. CI installs, among others:

- clang/lld/LLVM 18;
- CMake, Ninja, ccache, make, nasm and Meson;
- glslang/spirv tools;
- bison/flex and autoconf;
- binutils/coreutils/util-linux (including `ar`, GNU `realpath` and `flock`);
- git, curl, wget, unzip and rsync;
- Python **3.12+** with venv/pip/mako/yaml;
- librsvg and ImageMagick.

CI pins Meson to the version validated by the release workflow.

For Apple Silicon local iteration, install the host tools with Homebrew (LLVM 18, CMake, Ninja, ccache, NASM, Meson, glslang/SPIR-V Tools, bison/flex, pkgconf, autoconf, coreutils, flock and Python). `tools/host-env.sh` creates checkout-local `*-18` shims instead of modifying system tool names, and the Python helper environment lives under `.local/`.

The first Apple Silicon RADV preparation also builds the pinned LLVM 18 SPIR-V translator under
`.local/` through `tools/prepare-macos-llvm-spirv.sh`. It is a host build helper only; it does not
replace the PS5 cross compiler or become part of the installed Encore application.

## Crash reports

Encore writes crash reports under:

```text
/data/prosperoeden/logs
```

To symbolize one, use the exact unstripped ELF from the matching build:

```bash
python3 tools/symbolize-crash.py crash-YYYYMMDD-HHMMSS.txt \
  build/symbols/Prospero.Eden-Encore-R1.elf
```

## GitHub release workflow

The authoritative workflow is:

```text
.github/workflows/build-040-zbic.yml
```

It runs on pushes to the default Encore branch and can also be dispatched manually.

The build job:

1. checks out without persisting credentials;
2. installs the Ubuntu 24.04 toolchain;
3. pins Meson;
4. validates translations;
5. restores build caches;
6. performs `make release JOBS=4`;
7. saves caches only after success;
8. uploads `dist/` and symbols as a 14-day workflow artifact.

The publish job receives `contents: write` only after the build succeeds. Publication occurs when:

- a push commit message contains `[release]`; or
- a manual workflow dispatch sets `publish=true`.

Before publishing it checks `SHA256SUMS` against the ZIP and FFPFSC image. It then creates an
immutable tag of the form:

```text
encore-R1-<shortsha>
```

and publishes the ZIP, FFPFSC image and `SHA256SUMS` as the latest GitHub Release.

## Cutting an Encore release

Before the final `[release]` commit:

1. confirm the package/content version;
2. update the matching README `Changes in Encore R1` section;
3. keep `INSTALL.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md` and technical notes current;
4. require a green CodeQL run;
5. require a green shipping build/package run;
6. verify the generated checksums and Release assets;
7. keep the matching symbols artifact for crash reports.
