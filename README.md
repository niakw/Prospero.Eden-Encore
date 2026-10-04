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
