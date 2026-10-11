# R346–R347: Full standalone Encore Overrides and complete active Eden backports

Date: 2026-10-12. Source preservation, not a claim that FC27 now runs without stutters.

## R346 — 8,993 authored game profiles, direct versioned sources

- `niakw/encore-overrides` original pin `4fdb329e732a71878c1936b24759e58937c1ac18`, complete source tree in `vendor/sources/encore-overrides` and original upstream Git bundle bytes in `vendor/objects/encore-overrides`.
- Includes every 8,993 `games/*.json`, full manifest, general tiers and controller detection policy, glyph catalog, sources/scripts and GPL license. Snapshot is independently restored with `PROSPEROEDEN_DEPS_OFFLINE=1`, no GitHub needed.
- `tools/sync-encore-overrides.py` now reads and validates `VENDOR-ORIGIN.json` when the source is inside our repository; otherwise its old `git rev-parse HEAD` silently reported the outer Eden HEAD, not the profile DB pin.
- C++ snapshot was rebased from `0afb14f3` to `4fdb329e` **without changing the four general tiers or the only distinct FC27 profile**. There are 8,993 complete game records but only one truly game-specific settings set; all others use the general fallback. Do not present that as 8,993 unique tuned optimization policies.
- `tools/check-vendored-overrides.py` parses every catalog entry and per-game JSON, checks title IDs, settings, FC27 and compiled snapshot parity, glyphs and remote opt-in. `runtime-manifest.json` does not exist in the upstream repo, so startup no longer opens an HTTPS connection to a URL that is guaranteed to return 404. The optional updater can still be explicitly enabled through `EDEN_OVERRIDES_REMOTE_REFRESH=1` once its protocol has actual published source.

## R347 — 43 default Eden patch applications collapsed into 83 versioned source files

- Replayed the *real* `tools/apply-eden-backports.sh` on a clean full `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a` source tree, with all three experimental policies disabled. Obtained 43 independent SHA-pinned receipts and precisely **80 modified plus 3 added files**, a total of 83 source files, now fully readable in `vendor/encore-active/eden-backports/src/...`.
- The `tools/install-vendored-eden-backports.py` installer validates both original and active SHA of each source and refuses unknown source modifications; it atomically populates the ordinary mutable Eden build tree and emits original patch receipts for pre-existing source checks. Routine shipping compilation no longer calls `apply-eden-backports.sh` dynamically. The old script remains an independent replay oracle and is invoked only if a quarantined experimental patch is explicitly requested.
- `tools/install-vendored-eden-backports.py --replay` reconstructs all 43 transformations from pristine Eden, checks all 83 complete source files *and* all 43 individual original patch SHA receipts against checked-in files. This runs in source and native CI.
- Our previous 39-file `vendor/encore-active/eden-vulkan/` snapshot was generated incorrectly from **pristine** upstream Eden instead of Eden after ordered backports. Recreating Vulkan after the 43 shipping patches revealed exactly two mismatches:
  - `vk_buffer_cache_cost.cpp`: after GPU #4473/#4477 the old `KnownGpuTick()` method was removed in favour of `CurrentTick()/IsFree()`. R345's versioned C++ still defined it; PS5 native run `38184898869` consequently failed (`out-of-line definition ... does not match declaration`). The active translation unit has been corrected to match the actual patched compiled source, and cross-compiled for PS5 syntax.
  - `vulkan-cache/video_core/texture_cache/texture_cache.h`: the active snapshot had missed the newer PS5 read-only adjacent-view reuse and cache fix. It now matches the fully patched version.
- `tools/check-vendored-vulkan-fork.py` now stages an isolated original Eden source, installs the complete 83-file active backport set, then generates and verifies all 39 Vulkan translations. Thus, a repeat of the stale-original-source bug cannot pass future CI.

## Distinct follow-ups (not silently represented as migrated)

- CMake still contains many versioned CPU/JIT/HLE/OpenGL/renderer source adaptations not yet converted to full active source files. Those are already preserved as repository code, but their build-time CMake transformations remain and need their own source-equivalence migrations.
- The three experimental Eden patches are deliberately not part of shipping defaults due to separate guest/service lifecycle risks.
- Existing game-specific technical notes, visual glyph artwork mods, source Nlib assets and launcher options remain distinct from baseline video profile data. The repo's glyph catalog currently has zero curated title art rules; no executable Switch glyph atlas is silently promised.
- This project still requires native PS5 CI and, eventually, on-device measurements before declaring FC27's real hangs or graphics corrected.
