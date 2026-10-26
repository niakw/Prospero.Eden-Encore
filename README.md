<div align="center">
  <img src="assets/icon0.png" alt="Prospero.Eden Encore logo" width="154">

  <h1>Prospero.Eden Encore</h1>

  <h3>Console-native emulation, made for the living room.</h3>

  <p><strong>A controller-first PS5 emulator fork for firmware 13.60: NSP, XCI, NSZ, XCZ, NRO, NSO, NCA, NAX and KIP loaders, LZ4 + ZBIC/zstd decoding, TV navigation and reproducible builds.</strong></p>

  <p><strong>English</strong> · <a href="README.fr.md">Français</a></p>
  <p><kbd>Firmware 13.60 · hardware-tested target</kbd> <kbd>Vulkan + OpenGL</kbd> <kbd>TV-first UI</kbd> <kbd>Dynarmic</kbd></p>
  <p>
    <a href="INSTALL.md"><strong>Install</strong></a> ·
    <a href="#-why-encore"><strong>Benefits</strong></a> ·
    <a href="#-compatibility--current-limits"><strong>Compatibility</strong></a> ·
    <a href="#-builds--validation"><strong>Builds</strong></a> ·
    <a href="#credits"><strong>Credits</strong></a>
  </p>
</div>

<p align="center">
  <a href="https://github.com/niakw/Prospero.Eden-Encore/actions/workflows/encore-core-preflight.yml?query=branch%3Adev%2Fps5-sparse-jit"><img alt="Source and host validation" src="https://img.shields.io/badge/quality-source%20%2B%20host%20gates-465d87"></a>
  <a href="https://github.com/niakw/Prospero.Eden-Encore/actions/workflows/build-040-zbic.yml?query=branch%3Adev%2Fps5-sparse-jit"><img alt="Native build verification" src="https://img.shields.io/badge/build-native%20package%20checks-5e4db2"></a>
  <a href="LICENSE"><img alt="License GPL-3.0-or-later" src="https://img.shields.io/badge/license-GPL--3.0--or--later-31313a"></a>
</p>

<p align="center"><img src="assets/screenshots/encore-home.png" alt="Real Eden Encore Home screen captured from the C++/OpenGL launcher" width="860"></p>

> [!IMPORTANT]
> **FC27 performance — live master tracker:** [F07 P0/P1/P2 priorities and sparse-JIT qualification](docs/FC27_F07_MASTER_TRACKER.md). [F01–F06 host exit gates](docs/FC27_EXIT_GATES_2026-10-22.md) are separate from on-console playability. Source-review totals are not remaining optimization counts.
>
> **Firmware 13.60 is Encore's primary hardware-tested target, not a universal compatibility guarantee.** The launcher and selected titles have been exercised on this firmware, but game performance, saved control profiles and end-of-match stability still need work. Other firmware versions are **not** qualified. A current development build is **not** automatically a stable release.
>
> **Before a console test:** [source, logs, upstream and package checklist](docs/PRETEST_AUDIT_2026-10-14.md) — verify that the artifact and symbols match the exact tested SHA.

---

## ✨ Why Encore?

Emulation on a console is more than booting a game. It should be navigable from the couch, recoverable when settings go wrong and honest about what the hardware actually does.

| | What Encore brings |
| --- | --- |
| **🎮 TV-first experience** | Tropical-neon launcher, game artwork, recent titles, controller navigation, quick settings and language support. |
| **🧩 Game files and compression** | NSP, XCI, NSZ, XCZ, NRO, NSO, NCA, NAX and KIP selection; LZ4 and ZBIC/zstd decoding. Some files require extra program content to boot. |
| **🛟 Recovery without surprises** | One-session Safe Launch, confirmed resets and guarded migration without silently overwriting saved preferences. |
| **⚙️ Per-title profiles** | Minimum, Recommended, High and Ultra, plus Custom when you edit a preset. |
| **🎨 Graphics choices** | Vulkan/RADV and OpenGL, shader cache management, upscaling and anti-aliasing controls. |
| **🔍 Explainable performance** | Frame-time windows, guest/JIT activity, memory pressure, cache locks and IPC—not FPS alone. |
| **🔐 Safer native operation** | One-shot filesystem access, fail-closed recovery paths, bounded logs and package provenance checks. |

**Our approach:** preserve a working native foundation, select and adapt upstream improvements, then validate **source → native package → real hardware** independently.

<details>
<summary><strong>Encore vs the original port</strong></summary>

| Dimension | Original foundation | Encore's emphasis |
| --- | --- | --- |
| Hardware target | Broad upstream development | Firmware **13.60-focused** qualification |
| Launcher | Native frontend | TV-first hero, library, recents and quick settings |
| Content loading | Earlier formats | **NSP, XCI, NSZ, XCZ, NRO, NSO, NCA, NAX, KIP; LZ4 + ZBIC/zstd** |
| Recovery | Base defaults | Temporary Safe Launch and confirmed resets |
| Storage | Original path behavior | One internal/external root structure and guarded migration |
| Controller settings | Base mappings | Controller-first launcher profiles; game-owned actions still under investigation |
| Graphics | Upstream rendering | Pinned native adaptations and compiled-source evidence |
| Verification | Upstream test coverage | Host regressions, native packaging and device tests kept separate |

Encore is **not** an official upstream release or a promise that every newer upstream commit has been included.

</details>

---

## 📦 Game formats and executable compression

| Category | Formats | Current scope |
| --- | --- | --- |
| Library game containers | **NSP** (`.nsp`), **XCI** (`.xci`) | Existing game discovery and launch |
| Compressed game containers | **NSZ** (`.nsz`), **XCZ** (`.xcz`) | Experimental NCZ reader, games, updates and DLC; native and hardware qualification pending |
| Internal executable compression | **LZ4**, **ZBIC / zstd** | Existing NSO segment decoding; **not** game-file extensions |
| Direct-loader files | **NRO, NSO, NCA, NAX, KIP** | Selectable; successful execution depends on complete compatible contents. |

**Extracted ExeFS directories** are also discovered when `roms/<title>/` contains real, non-symlinked `main` and `main.npdm` files. They appear as `EXEFS` in the Library; this is a directory layout, not another ROM extension.

NCZ block compression permits random reads directly from the compressed file. Solid compression may unpack one running title to `/data/prosperoeden/user/cache/nsz/`; this can require approximately the full uncompressed game size. Outside a running game, bounded, validated pieces are reused for metadata reads. A developer build that contains the feature is not a console-tested release.

[Compressed games, space requirements and cancellation](INSTALL.md#compressed-nsz-and-xcz-games) · [Source and tests](headless/ncz.h) · [Complete format matrix](docs/CONTENT_FORMAT_MATRIX_2026-10-23.md)

---

## 🚀 Install Encore

> [!TIP]
> For a tested release, use [GitHub Releases](https://github.com/niakw/Prospero.Eden-Encore/releases), read the release's **specific firmware/gameplay validation notes**, and verify checksums. GitHub Actions artifacts are experimental unless separately qualified.

**Available packaging paths when published:** full ZIP with the application folder; optional FFPFSC image. The native title ID is `PPSA99008`.

**Application folder:** `/data/homebrew/PPSA99008/`.

**Persistent data root:** `/data/prosperoeden/`, containing `keys/`, `firmware/`, `roms/`, `updates/`, `mods/`, `save-import/` and `save-export/`.

Changing to external storage changes the **root**, not the subdirectory layout. Do **not** delete your persistent data root when upgrading an installation. Encore does not provide commercial software, keys, games or firmware.

**Full setup and upgrades:** [INSTALL.md](INSTALL.md) · [Build from source](docs/BUILDING.md) · [Support](SUPPORT.md).

---

## 🎛️ Built for the couch

| Feature | What to expect |
| --- | --- |
| **Home, Library, Recents** | Controller-friendly navigation, game metadata, cover/banner enrichment and offline fallback |
| **Animated game launch** | Real 3D rotating case with authentic scans per face when available. Missing front/back are reconstructed from cached game art, distinct screenshots, title and description by the native OpenGL renderer, without image generation. [Artwork details](docs/LAUNCH_CASE_ARTWORK.md) |
| **Quick Settings** | Per-title video changes without digging through debugging menus |
| **Video profiles** | **Minimum → Recommended → High → Ultra**; Custom after manual adjustment |
| **Safe Launch** | Conservative OpenGL, 1× internal resolution, 1080p, bilinear, handheld, 60 Hz and mods off for that run only |
| **Controls** | Native launcher mapping profiles, vibration and deadzones |
| **Languages** | Launcher catalogs for **29 languages**, including complex-script text shaping |
| **Visual tuning** | Resolution, filters, upscaling, sharpening and anti-aliasing options |

Safe Launch does **not** erase saves or permanently overwrite preferences. **Game-specific action binding** is distinct from the launcher's physical controller mapping, and is not yet fully proven for the main match test.

<details>
<summary><strong>Under the hood: CPU, graphics, JIT and memory</strong></summary>

- **Dynarmic remains the production JIT.** Experimental cross-core shared JIT and anticipatory compilation remain disabled in stable profiles due to unqualified concurrency/lifetime behavior.
- **Vulkan/RADV and OpenGL** are independent graphics routes. The native graphics build uses pinned source adaptations, tests, source fingerprints and archive checks rather than treating source presence as proof of compiled integration.
- **Shader cache** allocation and file size do not prove hit rate. Cold pipeline creation, long CPU waits and shader-cache reuse must be measured separately.
- **Memory** package declarations, sparse page tables, committed guest backing and JIT code-cache policies are not interchangeable. The single native PS5 release now selects demand-backed sparse RX/RW JIT aliases, with physical backing reclaimed only after a quiesced full-cache invalidation. Host checks exist; runtime memory savings and stability on firmware 13.60 remain unqualified, and physical memory is not unlimited.
- **Diagnostics** can distinguish a running compositor from actual guest progression; detailed capture has costs and is not automatically enabled in quiet gameplay.

See [Architecture](docs/PS5_NATIVE_ARCHITECTURE.md), [Performance roadmap](docs/PERFORMANCE_ROADMAP.md) and [Integration audit](docs/INTEGRATION_AUDIT_CPU_GPU_JIT_2026-10-14.md).

</details>

---

## 🧪 Compatibility & current limits

| Target | Evidence | Status |
| --- | --- | --- |
| **Firmware 13.60** | Device boot, launcher and selected title sessions | **Primary tested target** |
| Other firmware versions | No equivalent hardware qualification | **Not claimed** |
| Newer NSO content | ZBIC/zstd and LZ4 source/native paths | **Implemented; title-dependent** |
| Main match test | Gameplay captured across full sessions | **Stutters and end-match freeze unresolved** |
| Adventure title sessions | Previously reported broadly playable | **Not a universal compatibility claim** |
| Custom game actions | Launcher mapping ≠ guest's saved control actions | **In-match persistence unresolved** |
| In-game HUD freshness | Graphics activity can outlive guest progress | **Under investigation** |

**Performance, stated accurately:** the last available full-match capture (`2efd8b3c`) recorded **858 frame intervals above 50 ms**, ten above 500 ms and a prolonged guest-progress stall while presentation remained active. Later changes have passed various source/native checks; **no matching later device capture proves these changes improved FPS or removed the freeze**.

[Read the measured stress analysis](docs/FC27_STRESS_REPLAY_2026-10-14.md) · [Gameplay recovery plan](docs/GAMEPLAY_FREEZE_RECOVERY_PLAN.md)

> [!WARNING]
> A 30 FPS compositor counter is not proof that a game is advancing. Encore does **not** promise universal title compatibility, 60 FPS, glitch-free HUD updates or automatic conversion of custom gameplay bindings.

---

## 📦 Builds & validation

<kbd>dev/ps5-sparse-jit</kbd> · <kbd>Source & host checks</kbd> · <kbd>Native package checks</kbd> · <kbd>On-device qualification</kbd>

1. **Source and host gates:** lock in memory/JIT lifetime, launcher contracts, source-provenance assertions and trace-derived regressions.
2. **Native build:** compile, link, assemble, inspect the installable title and upload both application archives and debug symbols.
3. **Real hardware:** independently verify startup, controls, frame pacing, content freshness, gameplay progression and safe return to the launcher.

[Source preflight](https://github.com/niakw/Prospero.Eden-Encore/actions/workflows/encore-core-preflight.yml?query=branch%3Adev%2Fps5-sparse-jit) · [Native build artifacts](https://github.com/niakw/Prospero.Eden-Encore/actions/workflows/build-040-zbic.yml?query=branch%3Adev%2Fps5-sparse-jit) · [Build guide](docs/BUILDING.md)

Download an artifact from a **successful run matching the commit you want to test**, not a previous green build. Passing CI alone does not make a release.

## Changes in Encore R1

- A firmware-13.60-focused native port with a redesigned launcher, controller-first UX and one-session Safe Launch.
- ZBIC/zstd loading alongside the existing LZ4 path.
- Title-aware video presets, multilingual UI and guarded data migration.
- A pinned native graphics/toolchain integration with explicit provenance and regression checks.
- Reworked observability and crash-recovery paths, with open tracking of gameplay stutter, content freshness and saved in-game controls.

---

## 🛡️ Safety, independence and responsible use

Encore hardens one-shot filesystem operations and rejects unsafe migrations, but **filesystem access is not a post-elevation sandbox**. Bounded logs, pinned sources and automated checks reduce specific risks without making the environment infallible.

See [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SUPPORT.md](SUPPORT.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

This is an unofficial community fork. It does not ship copyrighted commercial games, firmware, keys or DLC, and it does not grant third-party distribution rights.

---

## Credits

Encore is built from and depends on the work of many upstream projects. The list below covers the
**direct repositories and pinned build/runtime inputs used by Encore**. Each entry identifies
its upstream author, known contributor or project-maintainer account; a project account is not
presented as the sole person who wrote its code. This list is not exhaustive; transitive dependencies of
Eden and the individual licence details are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Emulator and launcher foundations

- [ProsperoEden](https://github.com/blackbearreloaded/ProsperoEden) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — original PS5 emulator port/fork Encore is based on.
- [Eden](https://github.com/eden-emulator/mirror) — **Authors / maintainers: Eden Emulator Project team (`@eden-emulator`) and contributors** — emulator core used by Encore.
- [Citron Neo emulator](https://github.com/citron-neo/emulator) — **Authors / maintainers: Citron Neo team (`@citron-neo`); SM/audio fixes by `@HopeSuffers`** — upstream HLE ServiceManager/audio initialization fixes referenced by Encore's **disabled-by-default experimental** backport (not part of the current shipping binary).
- [ProsperoPuzzles](https://github.com/blackbearreloaded/ProsperoPuzzles) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — origin of the launcher drawing/text/animation/sound framework used by Encore.

### PS5 platform, graphics and packaging

- [PS5 Native App Boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — native runtime, packaging and base platform integration.
- [PS5 OpenGL](https://github.com/blackbearreloaded/ps5-opengl) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — OpenGL 4.6 runtime used by Encore.
- [Mihawk's PS5 Mesa](https://github.com/mihawk-99/PS5_Mesa) — **Authors / maintainers: Mihawk (`@mihawk-99`) and Mesa contributors** — Mesa/RADV source used by the Vulkan path.
- [Mihawk's PS5 Vulkan](https://github.com/mihawk-99/PS5_Vulkan) — **Authors / maintainers: Mihawk (`@mihawk-99`)** — PS5 Vulkan/RADV build and link recipes.
- [Mihawk's PS5 PayloadSDK](https://github.com/mihawk-99/PS5_PayloadSDK) — **Authors / maintainers: Mihawk (`@mihawk-99`) and upstream SDK authors** — PayloadSDK fork used by the RADV toolchain.
- [PS5 Payload SDK](https://github.com/ps5-payload-dev/sdk) — **Authors / maintainers: John Törnblom (`@john-tornblom`) and contributors `@ps5-payload-dev`** — PS5 homebrew SDK used by the native toolchain.
- [ps5-vulkan](https://github.com/mpereiraesaa/ps5-vulkan) — **Authors / maintainers: `@mpereiraesaa` and contributors** — earlier PS5 Vulkan platform work used by the graphics stack.
- [PSBrew/MkPFS](https://github.com/PSBrew/MkPFS) — **Authors / maintainers: PSBrew team (`@PSBrew`)** — optional reproducible `.ffpfsc` image packaging.
- [SharpProspero](https://github.com/SvenGDK/SharpProspero) — **Authors / maintainers: SvenGDK (`@SvenGDK`)** — source/reference used by the native packaging toolchain.

### Compatibility, media, text and build inputs

- [Encore overrides](https://github.com/niakw/encore-overrides) — **Authors / maintainers: `@niakw`** — companion database/source of the four general video tiers, title-specific overrides and the generated PlayStation Auto control profile.
- [ghost-land/Nlib-API](https://github.com/ghost-land/Nlib-API) — **Authors / maintainers: ghost-land team (`@ghost-land`) and contributors** — runtime title metadata and rich launcher media source (icons, 1080p banners, screenshots and local-player metadata).
- [kinnay/zbic](https://github.com/kinnay/zbic) — **Authors / maintainers: `@kinnay`; zstd source files from Atmosphère** — ZBIC/zstd NSO decompression support.
- [FFmpeg](https://github.com/FFmpeg/FFmpeg) — **Authors / maintainers: Fabrice Bellard (original creator), FFmpeg team and contributors** — H.264/VP8/VP9 decoding in the PS5 build.
- [HarfBuzz](https://github.com/harfbuzz/harfbuzz) — **Authors / maintainers: Behdad Esfahbod, David Corbett, Khaled Hosny and HarfBuzz contributors** — shaping for Arabic, Thai and other complex scripts in the launcher.
- [fmt](https://github.com/fmtlib/fmt) — **Authors / maintainers: Victor Zverovich (`@vitaut`) and contributors** — formatting headers used by build/runtime validation paths.
- [LLVM](https://github.com/llvm/llvm-project) — **Authors / maintainers: LLVM community (`@llvm`) and contributors** — compiler-rt pieces used by the PS5 cross build.
- [pacbrew](https://github.com/ps5-payload-dev/pacbrew-repo) — **Authors / maintainers: ps5-payload-dev team and contributors** — pinned PS5 OpenSSL/zlib packages.
- [zlib](https://github.com/madler/zlib) — **Authors / maintainers: Jean-loup Gailly and Mark Adler (`@madler`)** — pinned native dependency used by the PS5 toolchain setup.
- [Boost.Context](https://github.com/boostorg/context) — **Authors / maintainers: Boost.Context team and Boost contributors** — pinned context runtime source used by Eden's PS5 build.
- [Xbyak](https://github.com/herumi/xbyak) — **Authors / maintainers: Mitsunari Shigeo (`@herumi`)** — x86/x64 JIT assembler used by Dynarmic/Eden and adapted by Encore's JIT allocator path.
- [SPIRV-LLVM-Translator](https://github.com/KhronosGroup/SPIRV-LLVM-Translator) — **Authors / maintainers: Khronos Group and SPIRV-LLVM-Translator contributors** — macOS host-toolchain support for the graphics build.
- [stb](https://github.com/nothings/stb) — **Authors / maintainers: Sean T. Barrett (`@nothings`) and authors of stb components** — launcher font baking/system-font loading support.

### PS5 input/audio research reused directly

- [ps5-native-gamepad-input-research](https://github.com/blackbearreloaded/ps5-native-gamepad-input-research) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — native DualSense/gamepad integration reference/code.
- [ps5-audio-decoding-research](https://github.com/blackbearreloaded/ps5-audio-decoding-research) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — native audio integration reference/code.

All credit for the original projects belongs to their respective authors and contributors. Encore's
changes do not imply endorsement by those projects or their maintainers.

## Community

- [Contributing](CONTRIBUTING.md)
- [Support](SUPPORT.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## License and legal

Prospero.Eden Encore is an **unofficial community fork** distributed under
**GPL-3.0-or-later**. See [LICENSE](LICENSE). Third-party components keep their
own licenses and attribution; the component map is in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the collected full texts
are in [LICENSES](LICENSES/). Release ZIPs and the installable PS5 title carry
those notices; the standalone `.ffpfsc` therefore keeps a `legal/` directory
inside the installed title.

Encore is not affiliated with, sponsored by, endorsed by, or supported by Sony
Interactive Entertainment, Nintendo, the Eden Emulator Project, or other
upstream projects unless they expressly state otherwise. Product, project and
company names and logos are used only for attribution, compatibility
identification or description of upstream lineage. Copyright licensing does
not itself grant trademark rights.

No encryption keys, Nintendo firmware, commercial games, DLC, updates or other
proprietary console content are included. Use only software and console data
you are lawfully entitled to use.

Nlib is queried at runtime; Encore does not ship a pre-seeded Nlib media
library. Copyright/trademark rights in remote icons, banners, screenshots and
metadata remain with their respective rightsholders. Encore does not claim
that such remote media is public-domain, royalty-free or independently
redistributable.

The launcher SFX are generated locally and deterministically by
`tools/launcher/generate-sfx.py`; no third-party audio samples or external
generative-audio service output is included.

This project is provided **without warranty**, subject to the complete terms in
the applicable licenses.
