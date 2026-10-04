<p align="center">
  <img src="assets/eden-official.svg" width="150" alt="Eden logo">
</p>

<h1 align="center">Eden 0.40 Improved for PS5 13.60</h1>

<p align="center">
  A compatibility-focused PS5 fork built on ProsperoEden v1.000.040 and Eden.
</p>

## Why this fork?

This fork keeps the **v1.000.040** base, which works on PS5 firmware **13.60**, while adding targeted compatibility fixes without pulling in the newer Lapy-based elevation changes.

ProsperoEden v1.000.050+ changed the filesystem elevation path to Lapy. Lapy currently targets older firmware ranges, so on 13.60 newer builds can remain sandboxed and lose access to `/data/prosperoeden`.

The goal is simple: keep the working 0.40 behavior on 13.60, stay self-contained, and bring the PS5 experience closer to upstream Eden.

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


- **Stability and PS5 integration**
  - Keeps conservative Vulkan / 1x / 1080p / 60 Hz defaults, with OpenGL and per-game overrides available.
  - Preserves crash recovery, early guest-fault retry and useful GPU out-of-memory errors.
  - Uses asynchronous library scanning and bounded cover-texture caching so large libraries do not block the launcher or grow VRAM indefinitely.
  - Binds launcher input to the foreground PS5 user and keeps multi-controller hotplug support.
  - Hardens settings validation, package metadata checks and native RADV linking.


## Recommended settings

For a stable first run, keep **Vulkan**, **1080p output**, **1x internal resolution**, **Bilinear** and **60 Hz**.

- Use **OpenGL** as a compatibility fallback if a game has Vulkan-specific issues.
- Use **0.75x / 0.5x** when a game needs more performance; **FSR** is a good upscaler in that case.
- Use **1.5x+** only when the game has enough GPU/memory headroom.
- **120 Hz** is for compatible displays and titles/patches capable of higher frame rates; it does not by itself turn a 30/60 FPS game into 120 FPS.

## Changes in v1.000.040

- Keeps the self-contained ProsperoEden 0.40 filesystem elevation path for PS5 firmware 13.60.
- Adds ZBIC NSO decompression for newer Switch software.
- Adds PlayStation-first DualSense controls, per-game layout overrides, vibration strength and stick deadzone settings.
- Restores Eden's official visual identity for the launcher and PS5 app icon.
- Hardens clean-runner RADV packaging and build reproducibility.

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

The ZBIC loader path compiles successfully and passes the existing NSO loader checks. Controller and UI changes are PS5-specific. Hardware compatibility still depends on the individual title and should be tested on-console.

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
