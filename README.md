<p align="center">
  <img src="assets/eden-official.svg" width="150" alt="Eden logo">
</p>

<h1 align="center">Prospero.Eden Encore</h1>

<p align="center">
  <strong>The PS5 13.60-focused continuation of ProsperoEden 1.000.040.</strong><br>
  Stability first. Newer game support. Better recovery. Better PS5 UX.
</p>

<p align="center">
  <img alt="PS5 firmware 13.60 tested" src="https://img.shields.io/badge/PS5%20firmware-13.60%20TESTED-2ea44f">
  <img alt="ProsperoEden base 1.000.040" src="https://img.shields.io/badge/base-ProsperoEden%201.000.040-6f42c1">
  <img alt="ZBIC and LZ4" src="https://img.shields.io/badge/NSO-ZBIC%20%2B%20LZ4-blue">
  <img alt="DualSense first" src="https://img.shields.io/badge/UX-DualSense--first-8250df">
</p>

> [!IMPORTANT]
> **PS5 firmware 13.60 is the tested and primary target of Encore.**
> Other firmware versions are not currently claimed as validated by this fork.

## Why Encore?

Current ProsperoEden releases moved beyond the 1.000.040 base and use a newer Lapy-based elevation path. That newer direction brings useful features, but **13.60 is not one of the firmware versions currently validated by upstream's Lapy helper**.

Encore takes the opposite approach: keep the **known-working 1.000.040 filesystem path on 13.60**, then selectively add the compatibility, stability, recovery and usability improvements that are valuable on a PS5 today.

The result is not a blind downgrade and not a blind merge of newer upstream code. It is a **13.60-specific maintained branch** with its own hardening and release validation.

## Changes in v1.000.040

Prospero.Eden Encore turns the proven ProsperoEden 1.000.040 base into a PS5 13.60-focused release:

- PS5 firmware **13.60 tested** as the primary target.
- ZBIC/zstd NSO support for newer Switch software while retaining LZ4.
- One-shot filesystem elevation kept from the working 0.40 path and hardened with target validation,
  cloned-credential checks, verified rollback, fail-closed postconditions and symlink-safe migration.
- Safe Launch recovery profile without overwriting saved settings.
- Recommended / Smooth / Performance profiles.
- Global settings reset and per-game override reset.
- DualSense-first controls, vibration/deadzone controls and multi-controller handling.
- Diagnostics, bounded caches/logs and safer save import/export.
- Reproducible release packaging with ZIP, optional FFPFSC image and SHA-256 checksums.
- Complete French launcher catalog plus safe English fallback for incomplete translations.
- CodeQL, pinned GitHub Actions, Dependabot and documented security/community policies.

## The big advantages

### 🎯 PS5 13.60 is a first-class target

- **Tested target: PS5 firmware 13.60.**
- Keeps the 1.000.040 filesystem-access path instead of switching to Lapy.
- No Lapy daemon or Lapy helper dependency is required.
- If filesystem elevation is unavailable, Encore fails closed and stays sandboxed instead of pretending elevation succeeded.

### 🧩 Newer Switch software support

- Adds **ZBIC / zstd NSO decompression** used by newer Switch software.
- Keeps the existing **LZ4** loader path for older titles.
- Preserves ProsperoEden's PS5 low-memory NSO loading strategy.

### 🛟 Recovery built for a couch / TV emulator

- **Safe Launch** starts one game with conservative settings only for that run:
  - OpenGL
  - Handheld mode
  - 1x internal resolution
  - Bilinear
  - 60 Hz
  - 1080p
  - mods disabled
- Saved settings are **not overwritten**.
- One-button **Restore recommended defaults** globally.
- One-button **Reset overrides** per game.

### 🎮 DualSense-first UX

- PlayStation face-button layout by default.
- Nintendo layout remains available.
- Per-game controller-layout override.
- Adjustable vibration and stick deadzone.
- Multi-controller hotplug, motion controls and analog triggers retained.
- Launcher input follows the foreground PS5 user.

### ⚙️ Simple performance profiles

Instead of making every user understand seven low-level emulator switches first, Encore exposes:

- **Recommended** — conservative accuracy/stability.
- **Smooth** — compile-ahead oriented.
- **Performance** — more aggressive performance trade-offs.

Advanced settings and per-game overrides remain available.

### 🧰 Better diagnostics and bounded storage

- Filesystem-access status.
- Writable free space.
- Shader/JIT cache size.
- Log size.
- Safe shader-cache cleanup.
- RADV shader cache capped at **256 MB**.
- Session logs rotate instead of growing forever.
- Cover textures use a bounded LRU cache.

### 🔐 Extra hardening

- Save imports reject **symlink escapes**.
- Settings writes are atomic and invalid JSON falls back safely.
- Package metadata and native dependency closure are validated.
- Optional RADV/Mesa weak imports are resolved only after the real native link.
- Release inputs are pinned and release bundles are reproducible/checksummed.
- Keys, ROM/container files and local save-transfer folders are explicitly ignored by Git.

## Encore vs ProsperoEden upstream

This comparison is against **ProsperoEden v1.000.070**, the current upstream line this fork intentionally does not merge wholesale.

| Area | Prospero.Eden Encore | ProsperoEden v1.000.070 |
| --- | --- | --- |
| Main PS5 target | **13.60 — tested** | Lapy helper validated upstream on **6.02 and 12.70**; other firmware experimental |
| Elevation design | **1.000.040 one-shot sandbox elevator**, no Lapy dependency | Lapy-based exact-title helper / resident-service path |
| Newer NSO compression | **ZBIC + LZ4** | Upstream line evolves independently |
| Recovery | **Safe Launch + global reset + per-game reset** | No equivalent Encore recovery workflow documented |
| Performance UX | **Recommended / Smooth / Performance presets** | Seven individual performance switches |
| PS5 controls | **PlayStation-first simplified layout + per-game override** | Full button mapping system |
| Diagnostics | **Filesystem mode, free space, cache/log sizes, safe cleanup** | Crash/boot diagnostics and logs |
| Storage hardening | **Bounded RADV cache, rotating logs, bounded cover VRAM** | Shader cache / logging present, different policy |
| Save import safety | **Backup/rollback + symlink rejection** | Save import/export support |
| Updates | **Manual release updates by design** | Built-in network updater |

Encore deliberately chooses **predictability on 13.60** over importing every newer upstream subsystem.

## Firmware compatibility

| PS5 firmware | Encore status |
| --- | --- |
| **13.60** | ✅ **Tested target / supported release target** |
| Other firmware supported by underlying tooling | ⚠️ **Not validated by Encore yet** |
| Unknown/newer firmware layouts | ❌ **No compatibility claim** |

A firmware having offsets somewhere in the wider PS5 ecosystem does **not** automatically mean Encore has been validated on it.

## Filesystem elevation and security

Encore does **not** use Lapy. It keeps the 1.000.040 one-request elevation helper and hardens the interaction around it.

The helper:

- runs **once at startup**, not as a persistent service;
- talks only through the local ELF-loader connection on **127.0.0.1:9021**;
- accepts only one declared capability: **filesystem access**;
- validates a fixed, versioned **24-byte protocol**;
- accepts no arbitrary kernel pointer or privilege mask from the application;
- verifies the target **PID and exact title ID `PPSA99008`** before touching credentials;
- requires the application to clone its credentials before modification;
- confirms the credential pointer actually changed before writing;
- validates kernel pointers while finding the process;
- verifies the complete resulting credential/filesystem state after the write;
- attempts to restore the original state if applying elevation fails;
- uses bounded I/O timeouts and no unbounded retry loop;
- exits after the one request.

> [!WARNING]
Encore's elevation path is deliberately narrow and one-shot: it targets only the Encore title,
verifies the resulting state, verifies rollback on failure, and terminates instead of continuing
when post-elevation state cannot be trusted.

See [headless/elevation/README.md](headless/elevation/README.md) for the implementation-specific notes.

## Recommended defaults

Encore starts conservative:

| Setting | Default |
| --- | --- |
| Renderer | **Vulkan** |
| TV output | **1080p** |
| Internal resolution | **1x** |
| Upscaling | **Bilinear** |
| Refresh rate | **60 Hz** |
| FPS overlay | **Off** |
| Controller layout | **PlayStation** |
| Stick deadzone | **8%** |
| Vibration | **100%** |
| Console mode | **Docked** |

Try **OpenGL** when a title has a Vulkan-specific issue. Use **0.75x / 0.5x + FSR** when performance is the priority. Higher internal resolutions require substantially more GPU/memory headroom.

## Install

**ZIP is the recommended installation method.** Encore also ships an optional `.ffpfsc` image for
ShadowMountPlus users.

- **ZIP:** extract `PPSA99008` to `/data/homebrew/PPSA99008`.
- **FFPFSC:** mount the release image through a compatible ShadowMountPlus/etaHEN setup.
- Persistent Encore data lives under `/data/prosperoeden`.

See **[INSTALL.md](INSTALL.md)** for the complete step-by-step guide, update procedure, checksum
verification and troubleshooting.

## Build

Linux is recommended.

```bash
make release
```

Release files are generated under `dist/`.

The GitHub release workflow validates translations, performs the full native build/package pipeline, verifies SHA-256 checksums, and only publishes compiled assets after a successful build.

See [docs/BUILDING.md](docs/BUILDING.md) for toolchain details and [docs/FORK_NOTES.md](docs/FORK_NOTES.md) for the technical audit and validation history.

## Security

Encore uses CodeQL scanning, pinned build inputs, SHA-pinned GitHub Actions, checksummed release assets,
save-import symlink protection and a documented one-shot elevation security model.

Please report exploitable issues privately and avoid publishing proof-of-concept details before a
fix is available. See [SECURITY.md](SECURITY.md) for supported versions, scope and disclosure
instructions.

## What Encore intentionally does not claim

- It does **not** repair PS5 **FPKG entitlement/PPR** support.
- It does **not** make the 13.60 kstuff/FPKG stack reliable.
- It does **not** include keys, firmware, games or copyrighted console data.
- It does **not** silently import the newer Lapy elevation rewrite.
- It does **not** use an automatic renderer fallback that hides real failures.

FPKG/kstuff behavior is a separate jailbreak/runtime concern from the emulator itself.

## Credits

Encore is built from and depends on the work of:

- [ProsperoEden](https://github.com/blackbearreloaded/ProsperoEden)
- [Eden](https://github.com/eden-emulator/mirror)
- [PS5 Native App Boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate)
- [PS5 OpenGL](https://github.com/blackbearreloaded/ps5-opengl)
- [Mihawk's PS5 Mesa](https://github.com/mihawk-99/PS5_Mesa)
- [Mihawk's PS5 Vulkan](https://github.com/mihawk-99/PS5_Vulkan)

All credit for the original projects belongs to their respective authors and contributors.

## Community

- [Contributing](CONTRIBUTING.md)
- [Support](SUPPORT.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## License and legal

Prospero.Eden Encore is distributed under **GPL-3.0-or-later**. See [LICENSE](LICENSE).
Third-party components keep their own licenses and attribution; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

No keys, firmware, games or other copyrighted console data are included.

Use software and console data dumped from hardware and games you own. This project is provided
without warranty and is not affiliated with Sony Interactive Entertainment or the Eden project.
