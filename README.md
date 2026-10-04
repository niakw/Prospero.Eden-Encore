<p align="center">
  <img src="assets/eden-official.svg" width="150" alt="Eden logo">
</p>

<h1 align="center">Prospero.Eden Encore — PS5 13.60</h1>

<p align="center">
  A stability-, compatibility- and UX-focused continuation of ProsperoEden v1.000.040 and Eden.
</p>

## Why this fork?

This fork keeps the **v1.000.040** base, which works on PS5 firmware **13.60**, while adding targeted compatibility fixes without pulling in the newer Lapy-based elevation changes.

ProsperoEden v1.000.050+ changed the filesystem elevation path to Lapy. Lapy currently targets older firmware ranges, so on 13.60 newer builds can remain sandboxed and lose access to `/data/prosperoeden`.

The goal is simple: keep the working 0.40 behavior on 13.60, stay self-contained, and improve compatibility, recovery, performance tuning and everyday controller-first UX without blindly merging newer elevation code.

## Improvements

- **ZBIC NSO decompression**
  - Adds support for the ZBIC/zstd-compressed NSO segments used by newer Switch software.
  - Keeps the existing LZ4 path for older titles.
  - Based on Eden's upstream Switch 22.0+ ZBIC support.

- **PS5 13.60 focus**
  - Keeps the 0.40 built-in filesystem elevation path.
  - No Lapy dependency is required by this fork.

- **Build fixes**
  - Improves clean-runner build compatibility for RADV/Mesa weak Vulkan entrypoints.
  - Keeps optional RADV weak symbols out of PS5 dynamic imports.

- **DualSense-first controls**
  - PlayStation layout is the default: Cross = A, Circle = B, Square = X, Triangle = Y.
  - Switch back to the original Nintendo layout globally from **Settings > Controls**.
  - Override the controller layout per game from **Game settings**.
  - Adjustable vibration strength and stick deadzone.

- **Eden visual identity**
  - Uses Eden's official logo for the PS5 app icon, launcher branding and this README.
  - Replaces the custom green/scenic ProsperoEden look with Eden's dark violet/pink/blue identity.
  - Keeps the TV/controller-friendly PS5 launcher structure while moving the branding back toward upstream Eden.


- **Launcher quality-of-life**
  - Diagnostics shows filesystem mode, free space, shader/JIT cache size and log size, with safe shader-cache cleanup.
  - Save import/export supports Ryujinx and hand-copied saves, backs up replaced saves and rejects symlinked import trees.
  - On a fresh configuration, the game-language preference follows the PS5 system language once; later user choices are preserved.
  - Contextual help explains renderer, performance profile, output resolution, internal resolution, upscaling, refresh rate and controls for non-technical users.


- **Stability, recovery and PS5 integration**
  - Keeps conservative Vulkan / 1x / 1080p / 60 Hz defaults, with OpenGL and per-game overrides available.
  - Adds **Recommended / Smooth / Performance** profiles with clear trade-off descriptions.
  - Adds a one-shot **Safe Launch** from the Library: OpenGL + Handheld + 1x + Bilinear + 60 Hz + 1080p + mods off for that launch only, without rewriting saved settings.
  - Adds one-button **Restore recommended defaults** globally and **Reset overrides** per game.
  - Preserves crash recovery, early guest-fault retry and useful GPU out-of-memory errors.
  - Bounds RADV shader cache, session logs and cover-texture memory so noisy or long sessions cannot grow storage/VRAM indefinitely.
  - Uses asynchronous library scanning so large libraries do not block the launcher.
  - Binds launcher input to the foreground PS5 user and keeps multi-controller hotplug support.
  - Hardens settings validation, package metadata checks, native RADV linking and save imports against symlink escapes.


## Recommended settings

For a stable first run, keep **Vulkan**, **1080p output**, **1x internal resolution**, **Bilinear** and **60 Hz**.

- Use **OpenGL** as a compatibility fallback if a game has Vulkan-specific issues.
- Use **0.75x / 0.5x** when a game needs more performance; **FSR** is a good upscaler in that case.
- Use **1.5x+** only when the game has enough GPU/memory headroom.
- **120 Hz** is for compatible displays and titles/patches capable of higher frame rates; it does not by itself turn a 30/60 FPS game into 120 FPS.
- **Docked** is the normal PS5 console mode; try **Handheld** when a demanding title needs more performance or behaves better with the Switch handheld profile.

## Changes in v1.000.040

- Keeps the self-contained ProsperoEden 0.40 filesystem-elevation path proven on PS5 firmware 13.60; no Lapy migration.
- Adds ZBIC NSO decompression for newer Switch software while retaining the LZ4 path.
- Adds PlayStation-first DualSense controls, per-game layout overrides, vibration strength and stick deadzone settings.
- Adds Recommended / Smooth / Performance profiles, contextual settings guidance and conservative defaults.
- Adds one-shot Safe Launch, global recommended-settings reset and per-game override reset.
- Adds storage diagnostics, bounded RADV cache/log growth and safe shader/JIT cache cleanup.
- Hardens save import/export with backup/restore behavior and symlink rejection.
- Uses the PS5 system language for the initial game-language choice without overwriting later user preferences.
- Restores Eden's official visual identity and aligns project-facing branding with **Prospero.Eden Encore**.
- Hardens clean-runner RADV packaging, weak-import closure, reproducibility and release artifact generation.

## Recommended defaults

For a normal user, the fork starts with conservative settings:

- **Vulkan**
- **1080p TV output**
- **1x game resolution**
- **Bilinear scaling**
- **60 Hz**
- **FPS overlay off**
- **PlayStation button layout**

Video and controller screens show a short explanation for the selected setting, including when 120 Hz, FSR or higher render resolutions are useful.

## Install

1. Download the release ZIP.
2. Copy the included `PPSA99008` folder to:

```text
/data/homebrew/PPSA99008
```

3. Keep your existing data in:

```text
/data/prosperoeden
```

Updating the app folder does not require deleting your settings, saves, covers, logs, keys, firmware, or game files stored elsewhere.

## Build

Linux is recommended.

```bash
make release
```

Release files are written to `dist/`.

See `docs/BUILDING.md` for the full toolchain details.

## Status

This is an experimental fork focused on **Eden / ProsperoEden 0.40 + PS5 firmware 13.60**.

The ZBIC loader path and the native package pipeline are validated in CI; title-level compatibility still depends on the individual game and ultimately needs on-console testing.

**Important:** this project does **not** implement PS5 FPKG entitlement/PPR support. On firmware 13.60, FPKG installation/launch still depends on the separate jailbreak/kstuff stack, whose 13.60 support is not considered reliable by this project. Prospero.Eden Encore's release is a homebrew app package and does not claim to fix that external limitation.

For the complete technical change log, validation history, audit findings and planned improvements, see [docs/FORK_NOTES.md](docs/FORK_NOTES.md).

## Credits

This project is based on:

- [ProsperoEden](https://github.com/blackbearreloaded/ProsperoEden)
- [Eden](https://github.com/eden-emulator/mirror)
- [PS5 Native App Boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate)
- [PS5 OpenGL](https://github.com/blackbearreloaded/ps5-opengl)
- [Mihawk's PS5 Mesa](https://github.com/mihawk-99/PS5_Mesa)
- [Mihawk's PS5 Vulkan](https://github.com/mihawk-99/PS5_Vulkan)

All credit for the original projects belongs to their respective authors and contributors.

## Legal

No keys, firmware, games, or other copyrighted console data are included.

Use software and console data dumped from hardware and games you own.
