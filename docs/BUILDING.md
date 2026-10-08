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

## Source-only audit before an expensive native build

Before merging or triggering CI, review the full working-tree diff, then use the preflight
contracts and the configured compiler database to run **`-fsyntax-only -Werror` on modified native
sources with the actual `x86_64-sie-ps5` SDK flags**. A host-only macOS syntax check is insufficient:
PS5 `getnameinfo` declares `size_t` for buffer lengths, while the macOS header declares
`socklen_t`. The 2026-10-08 audit caught that difference before a native build.

Additional candidate preflight checks (these tests do not produce Encore application binaries):

```bash
python3 -B tools/check-network-runtime.py
python3 -B tools/check-fc27-trace.py
python3 -B tools/check-credit-attribution.py
# With the native CMake cache configured (no application build):
python3 -B tools/check-native-source-syntax.py "$(cat .local/headless-cache)/native-local"
python3 -B tools/check-ps5-net-unit.py
python3 -B tools/check-log-pipe-unit.py
python3 -B tools/check-bounded-logs.py
python3 -B tools/check-log-budget.py
python3 -B tools/check-home-media.py
python3 -B tools/check-ps5-backport-policy.py
python3 -B tools/check-release-hotpath.py
python3 -B tools/check-encore-ux.py
git diff --check
```

The shipping `tools/build-headless-native.sh --graphics` now runs the eight-unit native
syntax gate automatically **after CMake configuration and before Ninja**; its current-tree
compile database is mandatory. For a **local-only old cache** whose absolute paths still point
at an earlier checkout, use `--allow-stale` deliberately and treat that as a weaker audit, not
a release gate. No object or application binary is generated by the syntax pass.

These are not replacements for LLVM 18 Linux preflight, native linking, a successful package,
PS5 firmware 13.60 boot, or real application/gameplay validation. The separate HLE/JIT candidate
patches are intentionally disabled by default (`EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS`,
`EDEN_EXPERIMENTAL_ICACHE_COHERENCE`, `EDEN_EXPERIMENTAL_SM_HOST_WAIT`). Toggle only one per
isolated hardware A/B test and never silently package all three.

## Resuming a successfully compiled, failed-packaging PS5 application

CI run [#37710086280](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37710086280)
passed native compilation, native package inventory, alignment and imports,
and uploaded the staged app. It failed solely on the outdated
`tools/ci/check-staged-app.py` assertion for `kHomeCache`, removed from the
actual four-action Home utility navigation. The current identifiers are
`kHomeQuickPanel`, `kHomeQuickFirst`, `kHomeStorage`,
`kHomeControllers`, and `kHomeFullSettings`.

The staged artifact was downloaded locally and validated in full against the
corrected checker (**162 files PASS**). `tools/check-encore-ux.py` now rejects
staged-Home-checker references to missing UI identifiers in early preflight.

The workflow supports `workflow_dispatch` with
`resume_run_id=37710086280`, `publish=false`: download that already-built
staged title, revalidate it, assemble the distribution ZIP, FTP ZIP and FFPFSC
image, and upload the release artifact **without compiling PS5 code again**.
The commit message marker `[publish-existing]` suppresses a redundant native
build on the accompanying mainline push; it does not publish a GitHub Release.

## Preserving a prepared Eden source when a verified patch evolves

GitHub Actions restores the complete pinned Eden source and CMake/FFmpeg caches.
For the old Encore HTTP identification patch (SHA-256
`7117c1c3f353157b7fa46a86c6f77226b1183d9b374462cefe8b8dc5f32bf613`),
the updated patch only adds the missing `httplib::Result` error message.
`tools/apply-eden-backports.sh` now accepts *only* that exact old receipt,
verifies the old markers, upgrades the one `src/common/net/net.cpp` block,
revalidates and records the new patch digest. No source or dependency cache is
reset. Unexpected content or other changed patch hashes remain hard failures.
`tools/check-net-cache-migration.py` exercises successful upgrade,
idempotent resume and two rejection cases.

This addresses CI run [#37709504223](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37709504223),
which stopped in `make prepare` because a restored source cache contained the
older HTTP backport receipt; native compilation had not started.

## Two-stage experimental-backport validation in CI

The early `Validate startup, elevation and storage contracts` CI job step runs
*before* `make prepare`, so the runner does **not** have
`.local/headless-cache` yet. `tools/check-dummy-thread-waits.py` and
`tools/check-dynarmic-icache.py` validate patch syntax/required invariants at
that point and defer applying those **disabled-by-default** experimental patches.

After the pinned Eden source has been materialized, the native build preflight
re-runs both with `--require-pinned-source`, which rejects a missing fixture
and checks that the patch actually applies to the exact pinned files. Neither
check opts the experiment into a shipping build.

This corrects CI run [#37709145188](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37709145188),
which stopped before native compilation solely because the early static check
tried to read a not-yet-created local cache-path file.

## FC27 trace triage (no app build)

Use `python3 -B tools/analyze-fc27-trace.py path/to/session-log.txt --json` on an already
captured PS5 diagnostics log, and `python3 -B tools/check-fc27-trace.py` to validate the
analyzer's synthetic cases. An unchanged sampled guest PC only creates a **hypothesis**;
UI presentation FPS is not guest-frame progress. For the two independent FPS research paths
see [PERFORMANCE_ROADMAP.md](PERFORMANCE_ROADMAP.md).

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

It runs on pushes to `fix/0.40-zbic-13.60` and can also be dispatched manually. WIP branches do not trigger the shipping build.

The build job:

1. checks out without persisting credentials;
2. installs the Ubuntu 24.04 toolchain and pins Meson;
3. runs the source gates before the expensive native build: translations, release metadata,
   startup/elevation/storage contracts, video-profile contracts, Encore UX/media contracts and
   shipping-JIT stability;
4. restores dependency/native/ccache state;
5. prepares native dependencies;
6. builds and stages only the shipping app into `build/release/PPSA99008`;
7. saves caches immediately after successful staging;
8. uploads the staged app as a seven-day resumable artifact;
9. validates the staged app;
10. assembles `dist/` from that validated app and uploads `dist/` plus symbols.

A manual dispatch may set `resume_run_id` to a failed run whose staged-app artifact is already
green. In that mode CI downloads that exact staged app, skips toolchain/dependency/native compilation,
revalidates it and only reassembles the release files. This is the preferred recovery path for a
late packaging/upload failure and avoids paying for another full native compile.

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
