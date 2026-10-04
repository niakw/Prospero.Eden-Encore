# Eden 0.40 Improved — PS5 13.60 Fork Notes

This file is the technical continuity log for this fork. It records what diverges from ProsperoEden v1.000.040, why each change exists, what was validated, and what still needs hardware confirmation.

## Scope

- Base: ProsperoEden v1.000.040.
- Target console firmware: PS5 13.60.
- Working branch: `fix/0.40-zbic-13.60`.
- Goal: keep the self-contained 0.40 filesystem-access behavior that works on 13.60, while pulling in targeted compatibility, UX, build and stability improvements.
- Newer ProsperoEden >0.50/Lapy work is intentionally not merged into this branch.

## Compatibility and loader changes

### ZBIC NSO support

- Added ZBIC/zstd NSO decompression for newer Switch software.
- Detection matches Eden upstream: compressed NSO segments use flag bit 7 for ZBIC.
- Existing LZ4 path remains intact for older NSOs.
- ZBIC source is pinned as a dependency.
- ProsperoEden's PS5 low-memory/in-place NSO path is preserved.
- Host NSO memory checks were updated to understand the ZBIC helper.
- Compile-side validation has passed; final title-level validation still requires hardware testing.

### Why this was added

A newer title reached ProsperoEden's NSO loader and failed with `Core load failed: 43` / `ErrorLoadingNSO`, while older titles continued to boot. Eden upstream added ZBIC support for Switch 22.0+ after the Eden revision used by ProsperoEden 0.40.

## PS5 13.60 behavior

- Keeps the 0.40 built-in filesystem elevation path.
- No Lapy dependency is required.
- The PS5 Payload SDK used by this tree contains explicit firmware 13.60 offsets.
- Existing elevation remains the highest-risk code path because filesystem mode grants broad process credentials/capabilities. It is intentionally not refactored without hardware validation.
- `/` is rejected as a game-files directory to avoid scanning the console root.

## DualSense and controls

### PlayStation-first mapping

Default guest mapping on PS5:

- Cross -> Switch A
- Circle -> Switch B
- Square -> Switch X
- Triangle -> Switch Y

The original Nintendo-position layout remains available.

### Settings

Global controls now include:

- Controller layout: PlayStation / Nintendo
- Vibration on/off
- Vibration strength: 0-100%
- Stick deadzone: 0-20%

Per-game settings include a controller-layout override.

The launcher itself remains PlayStation-native regardless of guest layout:

- Cross = select/confirm
- Circle = back

### Existing controller support confirmed during audit

- Up to four players.
- Controller connect/disconnect updates while a game is running.
- Gyroscope and accelerometer.
- L2/R2 analog triggers mapped to ZL/ZR.
- Touchpad/Create provide Switch Minus where appropriate.
- Touchpad + L1 returns to the launcher.
- Touchpad + R1 toggles the FPS HUD on supported renderer paths.
- Launcher controller ownership now follows the foreground PS5 user, with initial-user fallback.

## Eden visual identity

- Added Eden's official logo asset from the upstream Eden repository.
- PS5 title name changed to `Eden 0.40 Improved` while keeping Title ID `PPSA99008`.
- PS5 app icon is generated from the official Eden SVG.
- Launcher brand asset is generated from the same source.
- TGA output is forced to uncompressed true-colour format and validated because the launcher TGA loader supports image type 2 only.
- Replaced the green/scenic ProsperoEden theme with a dark Eden-inspired violet/pink/blue palette.
- Removed legacy scenic launcher backdrops from runtime loading and from the final package.
- Asset regeneration tooling now uses the official Eden logo and no longer recreates the old scenic branding.

## Build and packaging hardening

### ZBIC build fixes

- ZBIC source is compiled into the common target.
- ZBIC include directory is explicitly exposed to that target.
- Clean-runner Meson and LLVM/SPIR-V dependencies were added to CI.

### RADV / Mesa native link

The PS5 RADV static archive contains many optional weak dispatch references.

A single-pass link allowed absent weak symbols to survive as native-title dynamic imports, which the PS5 package converter cannot satisfy.

Current strategy:

1. Perform a complete first native link with all real static/system providers.
2. Inspect only weak imports still unresolved after that full link.
3. Resolve those surviving optional hooks to address zero.
4. Perform the final link.
5. Reject the binary if any weak native import still survives.

This avoids inventing fake PS5 SDK exports while preserving any symbol actually provided by a real library.

### Package metadata

- Package title validation now expects `Eden 0.40 Improved`.
- Title ID remains `PPSA99008`.
- Package checker still validates required PS5 files and native dependency closure.

### Reproducibility

- Git dependencies are pinned.
- Release preflight now verifies every Git checkout matches its pinned commit.
- Development builds may still intentionally use modified local checkouts.
- Hosted GitHub runners can build releases; the fork no longer requires the original private self-hosted runner.
- Release publication receives write permission only in the publish job.
- Build caches include the main build caches and PS5 dependency checkouts.
- Duplicate future validation runs are configured to cancel in progress.

## Launcher and library audit

- Game scan runs asynchronously.
- Covers are loaded lazily.
- Cover textures are capped and least-recently-used entries are evicted.
- Launcher waits for an outstanding scan before destruction, avoiding use-after-free of launcher services.
- Settings are written through a temporary file + rename.
- Invalid JSON falls back safely.
- Per-game setting indexes reject values below -1 and values outside their option arrays.
- Library supports NSP/XCI discovery, title metadata, cover extraction, add-ons, language reporting, mods and recent games.

## Saves and mods

### Save transfer

Existing save-transfer code was audited:

- Ryujinx and hand-copied save discovery.
- Account/device saves handled separately.
- Existing target save is moved to a backup before replacement.
- Failed import removes partial output and restores the previous save.
- Export/re-import behavior is covered by host tests.

Remaining hardening candidate:

- Do not follow symlinks while importing a user-provided save tree.

### Mods

- Per-game global Mods switch.
- Per-mod enable/disable state.
- ExeFS/RomFS/cheat classification.
- Game-specific mods folder creation.
- Mod settings are applied on next launch.

## Runtime stability already present

- Vulkan is the default renderer at conservative 1x / 1080p / 60 Hz defaults.
- OpenGL remains selectable globally and per game.
- GPU failures are captured and returned to the launcher.
- Early guest faults can automatically retry up to four times.
- Out-of-memory rendering failures are translated into a useful lower-resolution message.
- Game shutdown stops input before core teardown.
- Audio output uses a stoppable worker and closes its native port cleanly.
- Crash reports retain addresses/registers but not arbitrary memory contents.
- Crash-report history is capped at five.
- Previous-session logs are retained for post-crash diagnosis.
- OpenGL shader cache is trimmed to a fixed budget.
- Cover texture memory is bounded.

## Stability/storage improvements identified by audit

These are not all implemented yet; they are the next safe candidates after the current validation build is green.

### High priority

1. **Bound RADV shader cache**
   - Mesa defaults to up to 1 GB when `MESA_SHADER_CACHE_MAX_SIZE` is unset.
   - Set a PS5-appropriate cap (candidate: 128-256 MB).

2. **Bound session logs**
   - `stderr.log` and `heap.log` are asynchronous but can grow for the full session.
   - Add a practical size/rotation policy so a noisy driver cannot consume writable storage.

3. **Symlink-safe save import**
   - Prevent save-tree imports from following symlinks outside the selected source tree.

4. **Translation refresh**
   - Add the new Eden/Controls strings to language catalogs, especially French.

5. **Repository safety ignores**
   - Explicitly ignore `prod.keys`, firmware dumps, NSP/XCI/NCA and local console/user-data outputs.

### Functional candidates

Priority order after the current build is validated:

0. **Contextual settings guidance**
   - Reuse the launcher's existing Accessibility help-text pattern for Video and Controls.
   - Show a short explanation/recommendation for the highlighted setting instead of making normal users guess what renderer/output/internal resolution/filter/120 Hz mean.

1. **Updates / DLC manager**
   - Eden already has native per-title `Settings::values.disabled_addons` support.
   - The PS5 port currently only scans and summarizes updates/DLC; it never exposes disabled add-ons.
   - Add a per-game list to enable/disable an update or DLC without moving files manually.

2. **FSR sharpening**
   - Eden exposes `fsr_sharpening_slider` (desktop default 25); the PS5 UI currently exposes FSR but hides its sharpening control.
   - Show the slider only while FSR is selected.

3. **Safe launch / recovery**
   - Development builds already contain a Vulkan -> OpenGL recovery path.
   - Promote the idea to a user-facing, explicit safe launch rather than enabling an opaque automatic fallback: conservative renderer/resolution/60 Hz and optionally mods off for one launch without overwriting saved settings.

4. **Diagnostics dashboard**
   - Expand Diagnostics beyond setup + detailed logs.
   - Show writable free space, shader-cache size, log size, active renderer, last crash state and filesystem-access mode.
   - Provide safe cache/log cleanup actions that never touch saves, firmware, keys or game files.

5. **Library quality-of-life**
   - Favorites.
   - Sort by name / recently played / favorite.
   - Optional compact compatibility note per title.
   - Search is lower priority on a controller-only TV UI unless an on-screen keyboard is added.

6. **Per-game controller tuning**
   - Layout is already per game.
   - Optional per-game deadzone/vibration strength can follow if real titles need different values.

7. **Controller calibration screen**
   - Live stick/trigger values and deadzone preview.
   - Useful for drift diagnosis and selecting the deadzone instead of guessing.

8. **Reset settings**
   - Global "Restore recommended defaults".
   - Per-game "Reset overrides" so renderer/resolution/filter/refresh/controller layout return to global settings in one action.
   - Per-row cycling already supports "Default"; the missing part is an obvious one-button recovery path.

9. **System-language first run**
   - The PS5 SystemService API exposes the console language (parameter id 1).
   - On a fresh settings file, initialize Eden's game/launcher language from the PS5 system language when it maps to a supported option.
   - Keep the saved language untouched after the user explicitly changes it.

10. **Console-mode guidance**
   - Keep Docked as the normal PS5 default for image quality.
   - Explain that Handheld lowers the guest's expected render/output profile and can help performance/compatibility in demanding titles.


1. **Per-game performance presets**
   - Safe / Balanced / Quality presets that populate renderer, internal resolution, filter and refresh while keeping advanced manual settings available.

2. **Per-game FPS HUD**
   - The FPS overlay is global today; making it overridable per title would match the rest of the per-game video settings.

3. **Per-game vibration/deadzone override**
   - Layout is per-game already; some titles may benefit from different deadzone or vibration strength.

4. **Controller calibration screen**
   - Live stick position/deadzone preview and trigger values in Settings > Controls.

5. **Renderer failure fallback / Safe launch**
   - A user-invoked safe launch could temporarily force conservative settings (1x, 60 Hz, known renderer) without overwriting the title's saved settings.
   - Automatic fallback should not be added blindly; it could hide real renderer bugs.

6. **Storage diagnostics**
   - Show shader-cache/log sizes and free writable space in Diagnostics.
   - Offer safe cache cleanup without touching saves/settings.

7. **Game compatibility notes**
   - Small per-title local note/status stored in the fork's config, useful for recording renderer/settings known to work.

8. **First-run / recovery profile**
   - If the launcher detects repeated crashes before a game reaches steady runtime, offer a conservative profile instead of repeatedly trying the same configuration.

## Deliberately not changed

- The 13.60 filesystem-elevation implementation is not being rewritten while the known 0.40 path works on hardware.
- No automatic renderer fallback is enabled yet.
- No unsafe deletion of user saves/settings/caches on upgrade.
- No keys, firmware or game files are included.
- The fork keeps `PPSA99008` to preserve the existing installation/data relationship.

## Validation history

Important CI findings during this fork:

- ZBIC initially failed because its include path was not visible to the common target.
- NSO memory harness then needed a ZBIC stub/update.
- Clean hosted runner exposed missing LLVM-SPIRV packages.
- RADV packaging exposed weak optional Mesa imports.
- Eden re-theme removed scenic code and caused `-Werror` on obsolete `kTau` / `noise()`; removed.
- Package title checker still expected `ProsperoEden`; updated.
- Launcher brand TGA generation was hardened to match the image loader's exact supported format.

The current reference validation run should be recorded here once it reaches a final result.


## Recommended user defaults

The PS5 launcher deliberately starts conservative. These are the recommended defaults for a normal user:

| Setting | Recommended default | Why |
| --- | --- | --- |
| Renderer | Vulkan | Native PS5 RADV path and the main performance target. OpenGL is a compatibility fallback. |
| Output resolution | 1080p | Lowest framebuffer/VRAM pressure and the safest TV output. 1440p/2160p increase output cost but do not increase the game's internal detail by themselves. |
| Internal resolution | 1x | Native game render scale. Use 0.75x/0.5x to recover performance; >1x only when the title has enough headroom. |
| Upscaling filter | Bilinear | Lowest-risk general default. FSR is a better quality choice when rendering below 1x; Bicubic is another quality option; Nearest is mainly useful for pixel-art/2D content. |
| Refresh rate | 60 Hz | Compatibility-first default. 120 Hz does not magically double game FPS; it is useful only when the game/patch can produce a higher rate and the TV accepts 120 Hz. |
| FPS overlay | Off | Turn it on for tuning or diagnostics. |
| Controller layout | PlayStation | Matches PS5 muscle memory. Nintendo layout remains available for titles where original button positions are preferred. |
| Stick deadzone | 8% | Conservative DualSense default. Increase if a stick drifts; lower only for a healthy/calibrated stick. |
| Vibration strength | 100% | Native full rumble. Reduce to preference. |
| Console mode | Docked | Best normal PS5 presentation. Try Handheld when a title needs extra performance or behaves better in handheld mode. |

### Planned UI guidance

The launcher already has contextual explanatory text for Accessibility rows. The same pattern should be reused for Video and Controls instead of adding more permanent clutter.

Planned Video help text:

- **Renderer:** Vulkan is recommended. Try OpenGL if a title crashes or renders incorrectly.
- **Output resolution:** Size of the final picture sent to the TV. 1080p is recommended for stability; higher output sizes use more memory and do not increase internal game detail on their own.
- **Resolution:** Internal game rendering scale. 1x is recommended; below 1x improves performance, above 1x improves image quality at a substantial GPU/memory cost.
- **Upscaling filter:** Bilinear is the safe default. FSR is recommended when using an internal resolution below 1x.
- **Refresh rate:** 60 Hz is recommended. 120 Hz only helps titles capable of higher frame rates and requires a compatible display.
- **FPS overlay:** Diagnostic display only.

Planned Controls help text:

- **Button layout:** PlayStation is recommended on PS5; Nintendo preserves the original Switch face-button positions.
- **Vibration:** Disables guest rumble without affecting PS5 system haptics.
- **Vibration strength:** Scales game rumble intensity.
- **Stick deadzone:** 8% is recommended; raise it to mask drift, lower it for more immediate response.

### Possible future display auto mode

The PS5 SDK exposes video-output resolution status APIs, so an `Auto (TV)` output mode is technically possible. It should not become the default until validated on hardware because automatically selecting 4K increases framebuffer/VRAM pressure and works against this fork's stability-first goal.


## CI validation ledger

| Run | Head / phase | Result | Data collected | Follow-up |
| --- | --- | --- | --- | --- |
| `37208757625` | early 0.40 ZBIC hosted build | Failed | Ubuntu Meson 1.3.2 was below the PS5 Mesa requirement. | CI upgrades Meson to >=1.4,<2. |
| `37209005362` | toolchain | Failed | `LLVMSPIRVLib` missing. | Added `llvm-spirv-18` and `libllvmspirvlib-18-dev`. |
| `37209346447` | deeper clean build | Failed later | Toolchain progressed past previous blocker. | Continued clean-runner hardening. |
| `37209589337` | 143/1597 | Failed | `headless/zbic_compression.cpp: zstd.c not found`. | Exposed the pinned ZBIC include directory to the common target. |
| `37211222037` | full compile | Failed post-link | ZBIC and `eden-headless` compiled/linked; old NSO memory harness did not know the ZBIC helper. | Updated harness for `std::span` / `DecompressDataZBIC`. |
| `37214268693` | packaging | Failed | All ZBIC/NSO checks passed; package conversion rejected `radv_EnumeratePhysicalDevices` as an unresolved native import. | Began RADV weak-import linker hardening. |
| `37225854300` / job `111505228821` | post-link RADV check | Failed | Large set of optional Mesa/RADV weak dispatch references survived the native link. | Reworked native link strategy; later generalized to a two-pass link. |
| `37227976171` / job `111511486244` | 1563/1597 | Failed | Eden re-theme removed scenic code but left `kTau` and `noise()` unused; `-Werror` stopped compilation. | Removed obsolete helpers. |
| `37229928282` / job `111517277606` | 1563/1597 | Failed | Same `kTau` / `noise()` compile failure; this run was already obsolete and confirmed the same blocker. | No new fix required; corrected in `7fb3823f…`. |
| `37229710339` | older RADV-validation head | In progress / obsolete | Older than the scenic-helper fix, so useful only as corroborating data. | Do not treat as release candidate. |
| `37230146719` | audited build, head `538fbef8…` | **Current reference run** | Contains ZBIC, DualSense, Eden UI, package-title fix, scenic-helper cleanup and two-pass weak-import linker. | Follow until build/package/artifact completes. |

### Rule for future CI failures

Every red run is inspected even if superseded. Record the first failing stage and exact error before discarding it: an older run can reveal a blocker that the newer run has not reached yet.
