# Prospero.Eden Encore — Technical Notes

This document is the authoritative technical close-out for the Encore fork.

## Scope

- Base: **ProsperoEden v1.000.040**.
- Primary console target: **PS5 firmware 13.60**.
- Hardware status: **13.60 tested**.
- Default branch: `fix/0.40-zbic-13.60`.
- Divergent archive/reference branch: `>0.50-bug_13.60`.
- Goal: keep the working 1.000.040 filesystem-access path on 13.60 while simplifying storage to
  one internal/external root with an identical folder schema.
- Newer ProsperoEden Lapy/elevation work is intentionally **not** merged wholesale.

## Firmware compatibility

| PS5 firmware | Encore status |
| --- | --- |
| **13.60** | **Tested / primary supported target** |
| Other firmware layouts supported by underlying tools | Not validated by Encore |
| Unknown/newer firmware layouts | No compatibility claim |

An offset existing in a payload SDK or another PS5 project is not treated as proof of Encore
compatibility. Hardware validation is required before adding a firmware to the supported table.

## Filesystem access

Encore does not depend on Lapy. It uses the proven 1.000.040 one-shot filesystem request for both
the default internal root and optional external storage.

### Storage model

- Default root: `/data/prosperoeden`.
- Optional external root: selected once as a root, not as separate per-folder paths.
- Required schema is identical under either root:
  `keys/`, `firmware/`, `roms/`, `updates/`, `mods/`, `save-import/`,
  `save-export/`, `ryujinx/`.
- App-managed config/logs/covers/user/cache/backups remain under `/data/prosperoeden`.
- An unavailable external root is not silently replaced by another location.

### Request model

- `main.cpp` requests `Capability::filesystem` once during single-threaded startup.
- The packaged helper is `/app0/sandbox-elevator.elf`.
- The application connects to the local ELF-loader endpoint at `127.0.0.1:9021`.
- If access is unavailable or validation fails, Encore remains sandboxed instead of reporting
  success.

### Safety / hardening properties

1. Fixed 24-byte, little-endian, versioned protocol.
2. Magic/version/message-kind/PID/status validation.
3. Only the declared `filesystem` capability is accepted.
4. No arbitrary kernel pointer, address or privilege mask is sent by the application.
5. Requested PID must resolve to exact title ID `PPSA99008`.
6. Kernel pointers are checked and process traversal is bounded.
7. Original credential/filesystem state is read before modification.
8. The application performs the same-UID credential-clone handshake first.
9. The helper refuses to write if the credential pointer did not change or the clone does not match
   the captured original state.
10. Elevated state is read back and must exactly match the intended state.
11. Failed apply attempts a full write-back and verification of original state.
12. Connect/send/receive operations have bounded five-second timeouts.
13. The helper serves one request and exits; no persistent service is installed.
14. The packaged ELF is structurally validated.
15. The application independently checks user/group identity after the helper returns.
16. `rollback_failed`, a failed request that changed identity, or a success with unexpected identity
    is fatal before privileged filesystem use.
17. Legacy sandbox migration rejects symlinks/unexpected file types.
18. Legacy game-file migration preflights the complete move, never overwrites conflicts and rolls
    back already moved directories if persistence fails.

The implementation-specific note lives in
[`headless/elevation/README.md`](../headless/elevation/README.md).

## Compatibility changes

### ZBIC NSO support

- Added ZBIC/zstd decompression for newer compressed NSO segments.
- Existing LZ4 decompression remains intact.
- Detection follows Eden's upstream ZBIC flag behavior.
- Pinned ZBIC source is built into the common target.
- ProsperoEden's low-memory/in-place PS5 NSO strategy is preserved.
- Host NSO memory checks understand the ZBIC helper.

This addresses newer software reaching the NSO loader and failing with
`Core load failed: 43` / `ErrorLoadingNSO` on the old loader path.

## PS5 UX and controls

- Four controller profiles are exposed: **PlayStation** (default), **Switch**, **Custom PS5** and **Custom Switch**.
- The untouched PlayStation profile is context-adaptive: PS-style Cross/Circle menu semantics are used initially, sustained stick/trigger activity can switch the face buttons to physical Switch gameplay positions, and menu/navigation evidence switches them back with hysteresis.
- The detector is title-agnostic. Its thresholds are generated from `encore-overrides/general/controls.json` into the same committed snapshot as the video profiles.
- Switch and both Custom profiles are deterministic and never rewritten automatically.
- Full DualSense button mapping is available globally and per game; per-game mappings can return to the global map.
- Vibration on/off and strength.
- Adjustable stick deadzone.
- Up to four controllers with runtime hotplug.
- Motion sensors retained.
- Analog L2/R2 guest trigger support retained.
- Touchpad shortcuts retained:
  - Touchpad + L1: return to launcher.
  - Touchpad + R1: toggle FPS HUD where supported.
- Launcher ownership follows the foreground PS5 user with initial-user fallback.
- Encore can replace its own button glyphs, but game-owned prompt textures remain title assets and are not universally replaced by input mapping.

## Performance and recovery

### Defaults

Fresh configurations start on the authored **Recommended** tier:

- Vulkan.
- 1440p TV output.
- 1.25x internal resolution.
- Bilinear scaling.
- FXAA.
- FSR sharpness 50% when FSR is selected.
- 60 Hz.
- FPS overlay off.
- PlayStation controller layout.
- 8% stick deadzone.
- Full vibration.
- Docked mode.

Existing saved preferences are not silently rewritten.

### Performance profiles

Encore exposes four authored, title-aware video tiers plus a derived Custom state:

- **Minimum** — Vulkan, 1080p, 1x, Bilinear, AA off, 60 Hz.
- **Recommended** — Vulkan, 1440p, 1.25x, Bilinear, FXAA, 60 Hz.
- **High** — Vulkan, 2160p, 1.5x, Bicubic, FXAA, 60 Hz.
- **Ultra** — Vulkan, 2160p, 2x, Bilinear, AA off, 60 Hz.

The authoritative profile data is generated from `niakw/encore-overrides`; title-specific overrides are applied before manual game settings. Shipping profiles keep Dynarmic **per-core JIT** and do not enable shared-JIT, successor batching or saved-block compile-ahead.

### JIT freeze revalidation

The 01:22 hardware freeze trace showed a guest core remaining inside Dynarmic at the same guest PC (`0x124AA117A8`) for many minutes while telemetry continued and PS5 submit/present timings stayed negligible. The current WIP therefore adds a narrowly scoped pre-emption check on **wall-clock LinkBlockFast backward/self edges** only. Forward links keep the zero-check fast path.

This is a **candidate fix under hardware revalidation**, not a resolved-freeze claim. It must pass the final native build and PS5 smoke/soak test before release status changes.

### Safe Launch

A Library Safe Launch is one-shot and does not rewrite saved preferences.

For that run only it selects:

- OpenGL.
- Handheld mode.
- 1x internal resolution.
- Bilinear.
- 60 Hz.
- 1080p output.
- Mods disabled.

### Reset paths

- Global **Restore recommended defaults**, requiring a second press to confirm.
- Per-game **Reset overrides**, requiring a second press to confirm.
- Mapping reset and shader/JIT cache clear use the same confirmation rule.

## Launcher and storage hardening

- Library scanning is asynchronous.
- Nlib enrichment provides cached title metadata, icons, **1080p banners**, up to three gameplay screenshots per title in the launcher, and local-player capacity; cache schema v2 refreshes older icon-only metadata once.
- Home uses a full-bleed Nlib banner when available, six compact recent-game cards, and a controller-first quick-settings gate that requires Cross before entering row editing.
- Cover loading is lazy and texture memory is bounded/LRU.
- Settings use temporary-file + rename semantics.
- Invalid JSON falls back safely.
- Per-game option indexes are range checked.
- RADV shader cache is capped at **256 MB**.
- Session logs rotate in bounded segments.
- Diagnostics reports filesystem mode, **free/total capacity of the selected Encore storage filesystem**, shader/JIT cache size and log size.
- Diagnostics can safely clear shader/JIT caches without touching saves, settings, keys, firmware or
  game files.
- Storage-root selection rejects `/` to avoid accidental console-root scanning.
- Internal and external roots use the same fixed folder schema.
- Save exports follow the selected storage root; app-managed backups/caches remain under the
  persistent Encore data root.
- Git ignores explicitly cover keys, ROM/container formats and local save-transfer data.

## Save transfer hardening

Supported transfer behavior:

- Ryujinx save discovery/import.
- Hand-copied save import.
- Account and device saves handled independently.
- Export to a re-importable folder.
- Existing target moved to backup before replacement.
- Failed import removes partial output and restores the previous save.

Security fix:

- A symlink at the import root is rejected.
- Nested symlinks are rejected.
- Host regression tests verify a selected save tree cannot escape through a symlink.

## Language and accessibility

- Launcher catalogs cover 29 PS5 language tags.
- French (`fr-FR`) is treated as the strict complete catalog in release validation and every packaged catalog is byte-checked.
- A language change rebuilds the launcher in-process so the catalog, system-font fallback and cached labels switch immediately.
- Release builds ignore the development-only `language.txt` override, preventing stale test files from forcing English.
- Other incomplete catalogs safely fall back to English for missing strings while still validating
  existing placeholders/fonts.
- On a fresh config, game language is seeded once from the PS5 system locale when supported.
- Later user language choices remain authoritative.
- Contextual help explains renderer, performance profile, output/internal resolution, filter,
  refresh rate and controller choices.

## Eden / Encore identity

- Uses `assets/icon0.png`, the supplied Eden Encore neon logo, as the single canonical project-facing raster asset.
- Encore branding is used in repo/release-facing surfaces.
- Existing Title ID `PPSA99008` is preserved to keep the installation/data relationship.
- Internal package-title validation remains deterministic.
- Launcher TGA assets are generated in the exact uncompressed format supported by the runtime.

## Audited upstream backports

Encore keeps the stable Eden/ProsperoEden base pin and applies narrowly reviewed fixes instead of a wholesale rebase:

- Eden **#4471** sparse-memory handling: the first-page bug is fixed and fully-zero sparse slots can release their owned backing and return to the shared zero mapping.
- Eden **#4473** dirty tracking: CPU/GPU modified-range handling for Kepler uploads and Maxwell macros.
- Eden **#4477** fence/synchronization cleanup, applied with #4473 as one coherent change.
- Reviewed FW23/service/max-session updates and runtime/HID fixes are applied through `headless/backports/` with exact patch checks.
- PS5 OpenGL is rebuilt from pinned source snapshot **`ad2807d`**. It contains the official SDK 1.0.1 vertex-buffer lifetime fix plus `217da45` (constant-buffer lifetime / vertex-binding alignment) and `67c873f` (one-time scanout-pool flush instead of an expensive whole-pool flush on every unbatched scanout write). `tools/build-opengl-sdk.sh` verifies the source commit and every installed manifest entry; the final candidate receipt freezes the exact produced SDK.

The Vulkan/RADV platform remains one coherent hardware-qualified baseline for R1: PS5_Vulkan `3f3ee696…`, PS5_Mesa `0b2d6d1a…` and Mihawk PayloadSDK `95c08f27…`. This is deliberate rather than an omitted update: the audited newer candidates (`fde9e379…`, `7b59ef27…`, `b5efad52…`) are a coupled platform migration. The Mesa branch diverges by roughly **107 commits ahead / 103 behind** and introduces a PS5 winsys, threaded layer, GS-compute path and broad RADV changes; the PayloadSDK branch diverges by roughly **100 ahead / 48 behind** and adds a new platform libc/elevation/memory stack. Those three must be migrated and hardware-qualified together. Mixing one member into the 13.60 release would be less safe than retaining the proven trio.

The image-quality baseline now comes from the authored `encore-overrides` tiers: Recommended uses 1.25x internal resolution with FXAA,
Bilinear output scaling and FXAA, while FSR sharpness defaults to 50% instead of the former aggressive
88%. Eden does not currently expose a reusable debanding post-process (the FSR source only contains
its own internal dithering). Encore therefore does not add an unmeasured fullscreen deband pass to a
release whose main performance target is 13.60; a future deband option requires PS5 frame-time and
image-capture evidence first.

## Native build and packaging hardening

### RADV / Mesa weak imports

The PS5 RADV static archive contains optional weak dispatch references.

Encore uses a two-pass strategy:

1. Link against the real static/system providers.
2. Inspect weak imports that still survive.
3. Resolve only the surviving optional hooks to address zero.
4. Perform the final native link.
5. Reject the binary if an unresolved weak native import remains.

This avoids inventing fake PS5 SDK exports while preserving symbols actually provided by real
libraries.

### Reproducibility and release

- Git dependencies are pinned.
- Release preflight verifies checkout revisions.
- Hosted GitHub runners build the release.
- Translation validation runs before the native build.
- Release publication has write permission only in the publish job.
- ZIP timestamps are deterministic.
- Release output includes SHA-256 checksums.
- Compiled ZIP / FFPFSC assets are published only after the build/package job succeeds.
- Unstripped symbols are retained as CI artifacts for diagnosis.

## Validation history

Key findings that materially changed the release:

| Run | Result | Finding / closure |
| --- | --- | --- |
| `37209589337` | Failed | ZBIC include path missing from common target; fixed. |
| `37211222037` | Failed | Host NSO harness did not understand ZBIC; fixed. |
| `37214268693` | Failed | RADV weak import survived native packaging; led to two-pass linker hardening. |
| `37227976171` / `37229710339` | Failed | Removed obsolete Eden-theme helpers rejected by `-Werror`. |
| `37230146719` | **PASS** | Full audited baseline reached build/package artifact generation. |

Later closure work added Safe Launch, resets, storage bounds, diagnostics, save hardening,
transactional ProsperoEden migration, the unified storage-root model, locale behavior, full French
catalog validation, title-aware overrides, Nlib rich-media UX and the release workflow. The current
WIP additionally carries the unvalidated guest-loop pre-emption candidate above. Publication remains
gated on a green shipping build **and** PS5 hardware revalidation of the release head.

## Deliberately excluded from this release

Encore does not silently pull features merely because they exist in a newer upstream branch.

Deferred/excluded:

- Lapy/newer elevation rewrite.
- Automatic renderer fallback that silently changes persisted behavior.
- Network auto-updater.
- Large multi-profile/player subsystem.
- Cheat/patch-library expansion.
- Favorites/search/local compatibility database.
- New update/DLC enable-disable manager.
- Extra per-title vibration/deadzone/FPS-HUD overrides without a demonstrated need.
- Controller calibration screen.

## PS5 FPKG / kstuff boundary

Prospero.Eden Encore does **not** implement or repair PS5 FPKG entitlement/PPR support.

On firmware 13.60, FPKG installation/launch remains a separate jailbreak/kstuff concern. The
presence of profiles or offsets does not make that path reliable, and failures such as
`CE-109297-8` must not be presented as emulator regressions fixed by Encore.

Encore's own homebrew application build, filesystem path and emulator runtime are validated
separately from that external limitation.

## 13.60 startup revalidation

The next stable release is gated on the fast startup/elevation/storage checks plus a successful native build and a hardware smoke test. A green compile alone is not treated as hardware validation.

## Separate CPU/HLE and frame interpolation investigation

The detailed, non-shipping investigation is in [PERFORMANCE_ROADMAP.md](PERFORMANCE_ROADMAP.md). A new offline diagnostic `tools/analyze-fc27-trace.py` reports native present gaps, possible recurring sampled guest PCs and HLE timings without claiming that host FPS equals gameplay progress. The first objective is still to cure FC27 freezes using controlled JIT/HLE A/B sessions. The separate high-impact research goal is a 30-real-to-60-presented-FPS pipeline via optical flow; it cannot repair a halted guest, and no PS5 interpolation implementation is available yet.

## 8 October 2026 — unreleased local post-#186 audit

**Working tree:** `/Users/admin/Downloads/Prospero.Eden-Encore-work`, branch `local/no-build-polish`,
base commit `149df7a`. This is **source-only work**, not the package available in GitHub Releases.
There has been no release build, local commit, remote merge, push, CI dispatch or PS5 gameplay test
of this lot. The confirmed #186 PS5 runtime still freezes/stalls FC27 intermittently.

- **Native source verification:** targeted `x86_64-sie-ps5` Clang `-fsyntax-only -Werror` caught
  and fixed a Home `const char*` concatenation error and a **PS5 SDK-specific** `getnameinfo`
  prototype mismatch that passed macOS checks. Home, Library, Settings, Launcher, main,
  diagnostics/services and performance source-only checks passed after correction.
- **Network:** PS5 native DNS shim uses `sceNetResolver` and `SO_NBIO` fallback where the native
  libc refuses `fcntl`. Bounds/overflow cases are covered in a mocked ASan/UBSan host test;
  `F_DUPFD`, `F_SETFL`, `F_SETFD` promoted `int` forwarding was corrected. PS5 HTTPS, CA-chain
  verification and real Nlib media retrieval are **not** yet tested.
- **Logs:** bounded startup stderr/heap and Eden file backend, with rotation, prune, and
  fault-injected `ftruncate` fallback. Worker-file-descriptor handoff is synchronized; Eden's
  `IOFile` can itself log failures, so the backend temporarily suppresses recursive logging
  during rotation. Host tests verify caps, tail retention and the failure path; PS5 remains untested.
- **HLE:** the service-manager host-worker wait and lazy audio service backport passes patch
  application and source-only C++ checks, but its shutdown/IPC effects are not qualified.
  It now joins dummy wait and Dynarmic I-cache proposals behind **OFF-by-default** opt-ins.
- **Graphics and UX:** the 16:9 hero and asynchronous Nlib enrichment are source-validated,
  not screenshot-confirmed. The `icon0.dds` is hash- and format-checked locally, but PS5 system
  overlay behavior is unknown. FC27 guest progress cannot be inferred from ~30 presented FPS;
  GPU and host-scheduling causality remain hypotheses. Frame interpolation is separate and not a
  remedy for a stuck guest.

**Additional prevention:** a new eight-translation-unit Clang `-fsyntax-only -Werror` gate
(`tools/check-native-source-syntax.py`) is wired into the graphical native build path **after
CMake config, before Ninja**, using the compiler's real PS5 include paths and ABI.

**Remaining release gates:** repeat full Linux/LLVM preflight, native compile and link,
inspect packaged files and imports, and complete PS5 13.60 boot + network + UI + overlay +
FC27 extended A/B tests. Do not merge, push or run the shipping workflow unless the remaining
source and integration issues are closed and the user-requested confidence threshold is met.
