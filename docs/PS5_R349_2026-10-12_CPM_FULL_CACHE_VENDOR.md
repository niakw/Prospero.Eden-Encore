# R349 — All 22 actually cached PS5 Eden CPM package sources directly in our repo

Eden's pinned `cpmfile.json` has 42 entries spanning all platforms/tests, not 42 PS5 compilation dependencies. Earlier R339–R348 vendored every top-level native source, full profile overrides, all 43 Eden backports, the entire Vulkan/Mesa RADV and OpenGL source families; **but CPMUtil** still relied on a persistent `~/.cache` for 22 packages (Boost, Vulkan headers, Sirit, fmt, Xbyak, SDL3, Zstd and others). This is real remaining external build-source exposure.

## What was captured

- The **complete exact active cached source trees** from the last validated PS5 native build, one package/version per folder: `vendor/sources/eden-cpm/<name>/<version>/`. Includes all upstream files, licenses, portable symlinks and original line endings. No submodules or remote Git pointers.
- SHA-locked provenance `vendor/sources/eden-cpm/VENDOR-CPM-LOCK.json`: full upstream pinned Eden SHA, entire pinned `cpmfile.json` SHA-256, source repo/tag/SHA-512 from that file, and deterministic SHA-256 of the entire content tree, total bytes and file counts.
- Includes 22 directories and **77,011 tracked actual source files**, ~866 MB of regular-file bytes / ~1 GiB of source-tree filesystem size. The 20 `cpmfile.json` entries not observed in this PS5 build remain explicitly listed as excluded; do not claim they were fetched or require them for the PS5 SKU without evidence.
- **These are exact original extracted source trees, not original compressed CPM archive bytes.** CPMUtil upstream tarball bytes are not consistently retained by the old source cache. The preserved cpmfile hashes/URLs remain useful for comparing future versions.

## How compilation consumes them

`tools/prepare-build.sh` stages vendored cached source trees after other cache inputs and before CMake/package build using `tools/vendor-eden-cpm.py --stage "$eden"`. The existing build cache stays incremental: any existing package-version folder is left in place, and only missing exact pinned-version sources are copied. `tools/vendor-eden-cpm.py --check` verifies all committed source trees against their deterministic checksums. Both source and native CI call this gate.

The captured source tree was independently restored from a clean empty temporary Eden cache on macOS to verify staging; this checks actual byte-preserving, no-network filesystem restoration, **not** proof that every tool downstream of CMake has zero remote dependencies. An end-to-end clean-cache PS5 build with outbound network blocked remains the final broader acceptance test.

## Beyond dependency relocation

This migration does not change GPU synchronization, guest threads or texture handling and therefore must not be presented as a fix for FC27 menu freezes or persistent saccades. Its value is eliminating changing upstream sources from the reproduction/diagnostics loop so further FC27 fixes can be reasoned about against one exact, auditable codebase.

R349 note: A full Git blob/working-source byte audit of 77017 paths found 69 normalized CRLF files; original byte copies and SHA256 checks are in vendor/objects/eden-cpm-eol-originals.*. The installer restores all 69 original files.
