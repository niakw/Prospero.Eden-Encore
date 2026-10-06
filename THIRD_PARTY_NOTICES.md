# Third-party notices

Prospero.Eden Encore is licensed under GPL-3.0-or-later (see [LICENSE](LICENSE)). It
builds on the following projects, each under its own license.

## Emulator

- **[ProsperoEden](https://github.com/blackbearreloaded/ProsperoEden)**, GPL-3.0-or-later. Encore is
  derived from its PS5 port/fork and keeps portions of its native integration and 1.000.040-era
  filesystem-access path.
- **[Eden](https://github.com/eden-emulator/mirror)**, GPL-3.0-or-later. The emulator core, built
  from the commit pinned in `UPSTREAM.json`, together with the dependencies Eden
  fetches and pins itself: Dynarmic, Boost, fmt, xbyak, zstd, lz4, Opus, SDL3,
  simpleini, sirit, SPIRV-Headers, Vulkan-Headers, Vulkan-Utility-Libraries,
  Vulkan Memory Allocator, ENet, frozen, cpp-httplib, nlohmann/json, and the time
  zone data. Each keeps its upstream license.
- **[FFmpeg](https://ffmpeg.org)**, LGPL-2.1-or-later. Built from Eden's pinned
  source with only the H.264, VP8 and VP9 decoders.
- **[OpenSSL](https://www.openssl.org)**, Apache-2.0, and
  **[zlib](https://zlib.net)**, zlib license. Taken from the
  [pacbrew](https://github.com/ps5-payload-dev/pacbrew-repo) PS5 packages.
- **[kinnay/zbic](https://github.com/kinnay/zbic)**, used for ZBIC/zstd NSO decompression.
- **LLVM compiler-rt** `emutls.c`, Apache-2.0 WITH LLVM-exception.

## Graphics

- **[PS5 Mesa](https://github.com/mihawk-99/PS5_Mesa)** and
  **[PS5 Vulkan](https://github.com/mihawk-99/PS5_Vulkan)** by Mihawk. The
  RADV Vulkan driver (Mesa, mainly MIT) and its PS5 link recipe and platform
  layer (GPL-3.0-or-later).
- **[ps5-vulkan](https://github.com/mpereiraesaa/ps5-vulkan)** by mpereiraesaa,
  an experimental Vulkan graphics and compute API for native PS5 homebrew.
- **[ps5-opengl](https://github.com/blackbearreloaded/ps5-opengl)**,
  GPL-3.0-or-later, which includes Mesa components under their own licenses. Encore R1 pins
  source commit **`ad2807d41cef2681882a9ee0d20808779f74b7cd`** in `tools/deps.json` and rebuilds
  its OpenGL 4.6 SDK with the upstream pinned/hash-verified inputs. That snapshot contains SDK
  1.0.1 plus the reviewed `217da45` constant-buffer/alignment and `67c873f` scanout-flush fixes.
  `third_party/app_heap.c` comes from it.

## Platform and interface

- **[PS5 Payload SDK](https://github.com/ps5-payload-dev/sdk)** by John
  Törnblom (ps5-payload-dev).
- **[Mihawk's PS5 PayloadSDK](https://github.com/mihawk-99/PS5_PayloadSDK)**, the fork pinned by
  Encore's RADV/Vulkan build path.
- **[PS5 Native App Boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate)**,
  GPL-3.0-or-later. The native app runtime, packaging tool and sandbox
  elevation helper (`headless/elevation`). Its packaging tool translates parts
  of SvenGDK's [SharpProspero](https://github.com/SvenGDK/SharpProspero).
- **[ProsperoPuzzles](https://github.com/blackbearreloaded/ProsperoPuzzles)**,
  GPL-3.0-or-later. The launcher's drawing, text, animation and sound code
  (`headless/prosperoeden/pe`) started there.
- **Montserrat** by Julieta Ulanovsky and contributors, SIL Open Font License
  1.1 (`third_party/fonts`). The launcher's font is baked from Montserrat Medium.
- **[HarfBuzz](https://github.com/harfbuzz/harfbuzz)**, "Old MIT" license (its
  `COPYING` file). Shapes the launcher's text in the scripts that need it, such
  as Thai and Arabic. Fetched at the release pinned in `tools/deps.json`.
- **[stb](https://github.com/nothings/stb)** by Sean Barrett, MIT or public
  domain (`tools/launcher/stb`). `stb_truetype` bakes the launcher's font and,
  in the app, reads the console's system fonts for the scripts Montserrat does
  not have. Encore carries a small local integer-width hardening patch for the
  host font baker; the otherwise-unused `stb_image_write` header was removed.
- The launcher's sound effects were generated with
  [ElevenLabs](https://elevenlabs.io) and edited for this project.
- `third_party/ps5_pad.hpp` comes from
  [ps5-native-gamepad-input-research](https://github.com/blackbearreloaded/ps5-native-gamepad-input-research),
  and `third_party/native_audio.hpp` from
  [ps5-audio-decoding-research](https://github.com/blackbearreloaded/ps5-audio-decoding-research).
  Both are GPL-3.0-or-later.

## Thanks

ProsperoEden exists thanks to the Eden maintainers and contributors, Mihawk,
mpereiraesaa, John Törnblom, SvenGDK, and the whole PS5 homebrew community.
