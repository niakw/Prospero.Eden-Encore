# Eden Encore — complete vendored dependency sources

This is the **actual content of our pinned dependencies**, included directly in this Git repository to make auditing, reproducibility and disaster recovery possible even if any upstream repository disappears. All licences, notices and source files that the upstream archives or Git snapshots contain are preserved. See `tools/deps.json` for the exact URLs and pinned commits/checksums. `vendor/sources/` contains full readable upstream source trees at their locked revisions; `vendor/objects/` contains byte-for-byte original source archives, Git packs and binary SDK packages split into **40 MiB or smaller Git-trackable chunks**, with a SHA-256 for every chunk and a SHA-256 over the whole reconstructed object. No Git LFS subscription or separate upstream clone is necessary to possess the complete inputs.

## What is included

| Name in `tools/deps.json` | Here | Type |
| --- | --- | --- |
| eden | `sources/eden/`, `objects/eden/` | Pinned full emulator source plus original tarball |
| ffmpeg | `sources/ffmpeg/`, `objects/ffmpeg/` | Pinned full FFmpeg source plus original tarball |
| fmt | `sources/fmt/`, `objects/fmt/` | Full fmt source plus original tarball |
| zbic | `sources/zbic/`, `objects/zbic/` | Exact Git worktree and source-pack preserving the upstream SHA |
| compiler-rt | `sources/compiler-rt/` | Eight individually SHA-256-pinned LLVM emutls/runtime source files |
| pacbrew | `objects/pacbrew/` | Entire third-party binary PS5 toolchain archive, split into small chunks |
| opengl-source | `sources/opengl-source/`, `objects/opengl-source/` | Exact Git snapshot and source-pack |
| harfbuzz | `sources/harfbuzz/`, `objects/harfbuzz/` | Full HarfBuzz source and tarball |
| boilerplate | `sources/boilerplate/`, `objects/boilerplate/` | Exact native app boilerplate source and Git snapshot |
| ps5-vulkan-tools | `sources/ps5-vulkan-tools/`, `objects/ps5-vulkan-tools/` | Complete Mihawk PS5_Vulkan repository at the build's pin |
| ps5-mesa | `sources/ps5-mesa/`, `objects/ps5-mesa/` | Complete Mihawk Mesa/RADV source at the build's pin |
| ps5-payload-sdk-fork | `sources/ps5-payload-sdk-fork/`, `objects/ps5-payload-sdk-fork/` | Complete Mihawk SDK fork source at the build's pin |
| boilerplate setup inputs | `sources/boilerplate-setup-0/`, `objects/boilerplate-setup-{0,1}/` | zlib 1.3.2 full source and upstream tarball; complete binary PS5 payload SDK v0.42 ZIP |

The `pacbrew` and PS5 SDK ZIPs are *prebuilt external binary toolchains*, not buildable original source by virtue of having a ZIP. Their contents are nevertheless preserved completely. Other library/toolchain upstreams are not silently assumed: if a future bootstrap needs another external artifact, it must be added here and hash-locked.

## Use and verification

```bash
python3 tools/check-vendored-deps.py
PROSPEROEDEN_DEPS_OFFLINE=1 python3 tools/deps.py fetch
PROSPEROEDEN_DEPS_OFFLINE=1 python3 tools/deps.py verify
```

The dependency loader uses checked-in readable source trees for the archive-based inputs, presenting them to existing CMake consumers through isolated mutable `.deps` working copies. It restores the Git dependencies' **original upstream commit identity** from content-hashed chunks, using their shallow Git object pack and exact-SHA shallow boundary, into disposable working checkouts. This is **not** a Git submodule requiring any external service. Packages such as pacbrew and the v0.42 SDK reconstruct from their chunks before extraction. Set `PROSPEROEDEN_DEPS_CACHE` to an empty directory to check that no global cache is needed. The `PROSPEROEDEN_DEPS_OFFLINE=1` flag makes any missing source a hard error, never a network fallback.

The build-time adapters already in `tools/prepare-vulkan-port.py` and `tools/patch-radv-wsi.py` are **still applied to the disposable compiled copies**. They are kept during this first vendor-only migration to avoid destabilizing FC27; they can now be moved in reviewable commits into the readable vendored trees. Merely bundling sources does not prove these rendering fixes work on PS5.

`python3 tools/vendor_all_sources.py capture` refreshes vendor snapshots **only after intentional dependency version updates**; it must not run for routine builds. It never silently alters pinned SHAs. `python3 tools/vendor_all_sources.py verify` and the CI gate detect missing/corrupted source archives. Every upstream copyright notice and license remains governed by its original terms; downstream modifications should retain license headers and attribution.

## Active patched Vulkan fork (R342)

`vendor/encore-active/eden-vulkan/` contains **the 39 complete, human-readable generated Vulkan C++ and header files used by our PS5 renderer**, including R334–R337. CMake now copies these tracked files directly into its mutable build directory; it does not execute `prepare-vulkan-port.py` during normal configuration. Original pinned Eden source remains unchanged at `vendor/sources/eden/` and in the exact original archive. `tools/prepare-vulkan-port.py` remains solely as a compatibility/equivalence oracle while we move the remaining GPU thread/CMake-derived conversions into versioned source files. Validate equivalence using `python3 tools/check-vendored-vulkan-fork.py`.

## Active patched Mesa RADV/VideoOut fork (R343)

`vendor/encore-active/ps5-mesa/` contains the **five full exact C files used for the native PS5 RADV driver**, not tiny strings spliced into third-party source at build time. `tools/build-radv-dependencies.sh` stages Mihawk Mesa normally and then calls `tools/install-vendored-radv.py` to replace the staged compiler translation units with our complete tracked versions before the incremental RADV build. This also tracks VideoOut's lifecycle, refresh fallback, host memory protections and startup diagnostics. The old `tools/patch-radv-wsi.py` is retained as a **test-only source-equivalence oracle**; it no longer patches anything as part of a production PS5 build. `python3 tools/check-vendored-radv-fork.py` confirms all five files are byte-for-byte equal to the old effective build and exercises a clean installer, repeated installer and refusal to clobber an unexpected Mesa source revision.

Keep `vendor/sources/ps5-mesa/` untouched as the exact original SHA checkout for history/comparison. The same applies to original Eden code; only `vendor/encore-active/*` is our maintained PS5-specific fork. Other CMake-derived core/HLE/GPU transformations still need the same migration, and should not be silently declared complete.

## Active native PS5 GPU worker fork (R345)

`vendor/encore-active/eden-gpu/` holds the exact GPU worker sources, a shared GPU thread header and the stop-aware bounded SPSC queue header. CMake selects `gpu_thread_quiet.cpp` for normal PS5 builds or `gpu_thread_dev.cpp` for detailed diagnostics, and copies all three compiler inputs directly into its temporary build directory. The source and tests preserve the 32-command queue, worker shutdown/fences and dev-only clock probes without applying source-text replacements during native configuration. `tools/check-vendored-gpu-thread.py` reconstructs the legacy derived PS5 sources for both profiles and executes the actual new PS5 CMake branch; all copies must match byte-for-byte. Its normalization removes only the previous build-machine-specific absolute include prefixes, replacing them with normal headers available through the existing `headless` compiler include path.

Other Core/HLE/CPU/JIT and selected OpenGL CMake source rewrites still exist, are version-controlled, and are scheduled for the same conversion; the native Vulkan, Mesa and GPU worker portions are now checked-in complete source translations.
