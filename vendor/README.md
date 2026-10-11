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
