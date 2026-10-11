# R343 — Versioned RADV/VideoOut compiler input replaces build-time source rewriting

Branch `dev/ps5-sparse-jit`. Original pinned Mesa input remains `vendor/sources/ps5-mesa` at commit `0b2d6d1a61d9bbf89cf8beb88a696144f67c61f8`; the full *modified* compiled C translation units are maintained in `vendor/encore-active/ps5-mesa/`.

## What changed

- Materialized exactly five full RADV/VideoOut `.c` units from our R341 source generator `tools/patch-radv-wsi.py`, preserving **byte-for-byte** the actual previously compiled source. They include `src/vulkan/wsi/wsi_common_videoout.c` (VideoOut lifecycle/120Hz/stop), PS5 address protection, win-sys queue init diagnostics, physical-device init diagnostics, and the unchanged pinned command-buffer unit (the last intentionally confirms no forced extra CPU flush code).
- `tools/build-radv-dependencies.sh` still stages Mihawk's pinned source via the native build, but then uses `tools/install-vendored-radv.py` to install **these actual versioned sources** into the temporary staged Mesa tree before an incremental rebuild. The production build no longer invokes the rewrite generator. The install validates that each original staged TU is either the pristine pinned source or our exact active file and **refuses unknown source drift**. It invalidates the old build provenance receipt only if any compiled source changed.
- `tools/patch-radv-wsi.py` now supports `--oracle vendor/sources/ps5-mesa TEMP_DIRECTORY` for independent byte-comparison and `--check RECEIPT` for direct hash comparison to the checked-in WSI translation unit. It is not part of the production build. The offline `prepare-build.sh` can still quickly detect an outdated WSI receipt without accessing the old upstream Git checkout.
- Source-only CI and native PS5 CI run `tools/check-vendored-radv-fork.py`: verifies all five files against pinned upstream + historical generator, confirms idempotent installer and unknown-source rejection. Native build checks continue to validate exact final `EDEN_WSI_SHA256` receipt and true RADV static link.

R342 similarly stores its 39 patched Vulkan translation units as actual files in `vendor/encore-active/eden-vulkan/`, copied into the CMake build directory instead of running the generator. Both upstream source trees are unchanged and their original SHA Git packs remain restorable completely offline.

## Remaining core migration

The large `headless/CMakeLists.txt` derives and rewrites more CPU/JIT, GPU-thread, HID/HLE and renderer source units from pinned Eden using `file(READ)/string(REPLACE)` during CMake configuration. R343 **does not claim those unrelated transformations are gone**. They need an equivalent source materialization and build selection with an exact-source regression test. Nor does R343 claim the reported FC27 in-match stutters, grass/HUD pixelation or controller-menu freeze are fixed.

## Reproducible pinned HUD shaders

The old Vulkan generator invoked the installed `glslangValidator` and `spirv-val` during every CMake reconfiguration. R342 compiles the two byte-for-byte tracked SPIR-V modules directly. Its source-only equivalence fixture verifies the unmodified GLSL shader source SHA-256, then uses the already-validated versioned SPIR-V to rebuild the generated C++ shader header in test mode; no CI runner-specific `glslangValidator` or non-deterministic SPIR-V differences are needed. Non-oracle manual generation still invokes the real shader compiler and validator.

## R344 portability fix

The R343 source-only GitHub CI correctly detected that the previous source generator had embedded a Mac-specific absolute path in `vk_pipeline_cache_cost.cpp`: `#include "/private/tmp/eden-dev-integration/headless/performance.h"`. R344 replaces it with `#include "performance.h"`, an already supported header in `target_include_directories(video_core PRIVATE ... "${EDEN_PORT_DIR}")`. Exact source generator equivalence is retained, and the preflight now bans checkout-specific absolute includes in versioned Vulkan source. The native R343 build was still in progress when this fatal portability issue was found, so it cannot be used as proof; only R344 native compilation can qualify the new source fork.
