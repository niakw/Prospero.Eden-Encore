# Native build recovery, vendored sources and upstream assessment

Audit of `dev/ps5-sparse-jit` — 14 October 2026.

## Red native build: actual cause and repair

The build [38478857146/job/115576208233](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38478857146/job/115576208233) failed in the **pre-build source/host gate**, not in the compiler. Both that job and its independent Linux source preflight rejected a mismatch in exactly one tracked file:

`vendor/encore-active/eden-vulkan/vulkan_swapchain.cpp`

The generator/oracle `tools/prepare-vulkan-port.py` had been updated for native bounded image acquisition, obsolete-swapchain handling and deferred suboptimal-image recreation, but the *compiled, versioned* Vulkan fork had not been updated. The failure was **correctly caught** by `tools/check-vendored-vulkan-fork.py`. The three changes were applied verbatim to the tracked active C++ source; that exact-equivalence check remains mandatory, never bypassed. A subsequent native compilation is required before declaring a usable console build. No attempt has been made to relabel this historical red job as a successful build.

## What is actually vendored — and what is not yet consolidated

`vendor/sources/` contains all currently declared production dependency snapshots from `tools/deps.json`, including source snapshots, complete native toolchain object chunks and all pinned active CPM inputs for the current platform. `vendor/objects/` preserves archives and SDK binaries. This answers **source availability**, not **build integration**. The source trees include the exact original copyright/licenses and are not modified when applying Encore-specific patches.

The five maintained native forks are in `vendor/encore-active/`: `eden-backports`, `eden-gpu`, `eden-surface-lifecycle`, `eden-vulkan`, `ps5-mesa`. The active Vulkan fork is already compiled directly: `headless/vulkan.cmake` performs `file(COPY ... vendor/encore-active/eden-vulkan ...)` and the old Python port adapter runs as an **equivalence oracle only**. Its CMake integration file under `headless/` is not evidence of a missing Vulkan source snapshot.

**The consolidation is nevertheless incomplete.** As of this audit, `headless/CMakeLists.txt` still contains **87 occurrences of `write_derived(`**, **98 of `file(READ`**, and **235 of `string(REPLACE`** (counts include support code and non-source rewrites; they are *not* 235 independent fixes). Native Core/HLE, JIT/memory, parts of the guest GPU stack and selected OpenGL code still use derived/overridden sources under `headless/`. This was explicitly recognized in `vendor/README.md`; it should never have been described as a *completed* active-source migration.

`tools/check-vendor-consolidation-debt.py` now checks that every `tools/deps.json` production source is still preserved and prevents increases in the above CMake rewrite counts, while `check-vendored-vulkan-fork.py` enforces byte-for-byte generation consistency. **These are regression gates, not an artificial "vendor migration complete" certificate.** The next migration should convert the remaining derived units to complete, maintained C++ translation units under `vendor/encore-active/eden-core/` with exact-source parity tests; transition each target one by one with a native compile gate. Do not delete source provenance, licenses, or user profile/override databases in this process.

Source inventory is distinct from a *universal* air-gapped build of all optional targets: `vendor/README.md` explicitly records 22 used PS5 CPM packages out of 42 possible cross-platform package declarations. The 20 other possibilities are not proof that a current PS5 production dependency is missing.

## Translation warnings: changed, not hidden

The historical build displayed **336 individual `warning: untranslated` lines** due to per-catalog truncation, while its per-catalog totals sum to roughly **5,982 warnings** across 29 catalogs. These include genuinely untranslated terms, obsolete entries and excessively long translations; 336 was never the full missing-translation count.

- Fully maintained **fr-FR**: eight overlong UI labels shortened, three stale translations deleted, and embedded French synchronized byte-for-byte.
- **fr-CA**: preserve existing local translations, fill missing current keys with maintained French rather than English, remove 62 obsolete entries, and shorten three overlong translations. Both French locales now target **zero missing keys and zero warnings**, enforced directly by `tools/launcher/strings.py check`.
- Other 27 catalogs: remove **61 obsolete source IDs each** (1,647 entries) rather than suppressing warnings. Already translated localized entries remain untouched. Their remaining missing strings are **genuine incomplete localization work**, not build errors we may silently conceal. Never assign fake English `msgstr` values to pass a coverage metric.
- `tools/check-launcher-translation-coverage.py` is a new audited CI inventory: it fails on obsolete entries, enforces exact coverage in both French locales, and fails if any other locale loses existing coverage. The count of remaining untranslated strings is visible in CI.

## Upstream [9ce26e65](https://github.com/blackbearreloaded/ProsperoEden/commit/9ce26e650e26112d958f6db4b20d93260de77825)

The commit “More free memory for demanding games (#156)” spans nine files. It implements several **different** mechanisms: page-on-demand guest memory backing, commit hooks for growing JIT code arenas, changes to x86 alias allocation, a reduced `flexibleMemorySize` request (320 MiB rather than the usual 448 MiB), and improved reporting of PS5 Pro direct-memory mode. Its objective is memory headroom/avoiding OOM rather than 30-FPS animation pacing.

**Do not cherry-pick all nine files blindly.** Encore already has separately qualified sparse JIT virtual ranges, source-derived x86 alias behavior and memory-allocation fallbacks; the upstream allocator rewrite intersects these guarantees. A 128 MiB shift from the flexible pool into direct memory may improve some content but also reduces the space available to the title/system libraries and cannot be assumed safe for the existing emulator/renderer/launcher. The upstream's “PS5 Pro” detection/reporting should not be conflated with memory available on a base console. Compare the guest-memory backing and flexible-pool requirements independently against our own allocation telemetry and existing fail-closed lifetime tests before integrating them. **Potentially worth adapting for memory pressure, not currently a justified fix for the reported stable-30-FPS judder.**

## Upstream [issue #97](https://github.com/blackbearreloaded/ProsperoEden/issues/97)

The open report describes an app freeze **after returning from console rest mode**, on **firmware 11.60** with a particular homebrew environment. It contains **no debug log or hardware trace**. That is a plausible Vulkan surface/swapchain lifecycle hazard and is relevant to a dedicated suspend/resume recovery test, but it is **not a reproduction of our firmware 13.60 game-session freeze while actively playing**. In particular, no rest/resume event was reported in the recorded FC27 28-minute GPU-stall trace. Treat these as separate failure classes until a common call site is proven; do not add generic forced restarts or timeouts to normal gameplay merely to make an unrelated suspend issue disappear.

## Validation gates

1. Re-run `tools/check-vendored-vulkan-fork.py` and `tools/check-ps5-native-acquire-failfast.py` in Linux source preflight, then compile the active fork in the native All-On build; block packaging if any check fails.
2. Run `tools/launcher/strings.py check` and `tools/check-launcher-translation-coverage.py` before source compilation. The two French locales must have no missing or obsolete translation and no overlong labels.
3. Run `tools/check-vendor-consolidation-debt.py` and existing vendor-source/binary/archive integrity checks; do not claim completion while generated source rewrites remain.
4. The original stable-30-FPS gameplay lag, title action mapping and sustained GPU freeze remain separate **open runtime defects**; successful host tests do not prove their resolution on hardware.

Validation request: re-run source preflight, warning-free maintained French checks, vendored fork exact-equivalence gate and one native All-On compile from the same head; no release/publish requested. The non-French translation coverage work and remaining derived-source migration are explicitly still open.


## Kernel header consistency follow-up (14 October 2026)

The paired native scheduler lock overlay now owns the slab header AND the
existing object-destruction guard in one maintained source. The old CMake
generated slab-header clone has been removed, preventing inconsistent header
layouts between core and the libraries that consume its public ABI. The JIT
CPU diagnostic is corrected to use the actual ArmDynarmic class member
m_system, rather than nonexistent m_parent, based on the failed native build
run 38495903010. This is source qualification until a new native build passes.
The remaining CMake rewrite count is still **not zero**.


## Locale completion (14 October 2026)

All 29 currently supported locale catalogs now contain 376 / 376 active
msgids each: **zero missing translations**, 2,775 previously empty entries
filled across 25 non-primary locales. The existing translations were not
replaced. Initial drafts for 23 languages came from machine assistance;
the remaining two Chinese variants used an original simplified translation
with the traditional variant converted by an offline OpenCC s2tw pass.
The tool checks all substitutions, forbids stale ids and verifies the
supported font glyphs where available, but **human linguistic proofreading,
truncation checks and physical system-font verification remain outstanding**.
These translations are not synthetic copies of the English msgid and must
not be represented as native-speaker certified. The new source coverage
gate fails if any supported locale loses a translation.

## Additional native CMake migration (14 October 2026)

Pinned-source-equivalent copies of the code loader and bounded error logger now live under `vendor/encore-active/eden-core/src`. Their generated CMake translation units have been replaced by maintained sources, and a source-parity regression gate checks both against their exact pinned transformations. The count is now **79 write_derived**, **89 file(READ** and **227 string(REPLACE** occurrences. Migration is incomplete, and native compilation on the new commit remains to be verified.

## Maintained audio units (14 October 2026)

The pinned native audio sink-selection unit and renderer voice-flag unit are now
versioned under `vendor/encore-active/eden-core/src`. Exact source-parity
checks ensure the native sink factory and SRC bit position keep their former
behaviour. The buffer-stream generation is **not** migrated or modified.
CMake generation debt is now **77 write_derived**, **87 file(READ**, and
**225 string(REPLACE** calls. This is source-only validation pending a fresh
native compile and is not a correction of the FC27 end-match freeze.
