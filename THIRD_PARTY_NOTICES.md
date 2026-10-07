# Third-party notices

Prospero.Eden Encore is a modified community fork distributed under
**GPL-3.0-or-later**. See [LICENSE](LICENSE). Third-party components retain
their own copyright and license terms.

This file is the attribution and provenance map for the release. Complete
license texts collected for the release are in [LICENSES](LICENSES/). The
installed PS5 title also carries `legal/LICENSE`, `legal/THIRD_PARTY_NOTICES.md`
and `legal/LICENSES/`, so the notices remain available when the installable
`.ffpfsc` image is distributed by itself.

Nothing in an open-source copyright license should be read as a grant of
trademark rights unless the applicable owner expressly says so.

## Emulator and compression

- **[ProsperoEden](https://github.com/blackbearreloaded/ProsperoEden)** —
  GPL-3.0. Encore is derived from its PS5 port/fork and retains portions of its
  native integration and 1.000.040-era filesystem-access path.
- **[Eden](https://github.com/eden-emulator/mirror)** — GPL-3.0. The emulator
  core is built from the commit pinned in `UPSTREAM.json`.
- Eden's pinned dependencies include **Dynarmic (0BSD), Boost, fmt, Xbyak, zstd,
  LZ4, Opus, SDL3, simpleini, sirit, SPIRV-Headers, Vulkan-Headers,
  Vulkan-Utility-Libraries, Vulkan Memory Allocator, ENet, frozen,
  cpp-httplib, nlohmann/json** and time-zone data. Each component retains its
  upstream license and copyright notices; the available full texts are bundled
  under `LICENSES/`.
- **[FFmpeg](https://ffmpeg.org)** — LGPL-2.1-or-later. Encore builds the
  pinned source with the H.264, VP8 and VP9 decoder subset used by the PS5
  media path.
- **[OpenSSL](https://www.openssl.org)** — Apache-2.0, and **zlib** — zlib
  license. The PS5 libraries come from the pinned
  [pacbrew](https://github.com/ps5-payload-dev/pacbrew-repo) package.
- **LLVM compiler-rt** pieces used by the PS5 cross-build are covered by the
  LLVM project's Apache-2.0 license with LLVM exception.

### ZBIC license selection

Encore pins **[kinnay/zbic](https://github.com/kinnay/zbic)** at commit
`11b08f2712264bbed731545085cbd9702096ceb7` for Nintendo Switch 22.0+ ZBIC
NSO decompression.

The kinnay/zbic repository itself contains a GPLv2 root license, but Encore
does **not** compile or redistribute its Python extension/module as a separate
dependency. The PS5 build includes only the snapshot's Zstandard implementation
files used by `headless/zbic_compression.cpp`. Those files state in their own
headers that they are dual-licensed under a BSD-style license or GPLv2 and that
the recipient may select either. **Encore selects the BSD-style terms for those
files.** The selected license text is preserved as
`LICENSES/ZBIC-zstd-BSD.txt`.
## Graphics

- **[Mihawk's PS5 Mesa](https://github.com/mihawk-99/PS5_Mesa)** and
  **[Mihawk's PS5 Vulkan](https://github.com/mihawk-99/PS5_Vulkan)** provide
  the RADV/Vulkan PS5 path. Mesa source files retain their upstream permissive
  file-level notices; Mihawk's PS5 platform/tooling repository is GPL-3.0.
- **[ps5-vulkan](https://github.com/mpereiraesaa/ps5-vulkan)** — GPL-3.0;
  experimental native PS5 Vulkan work used by the graphics stack.
- **[ps5-opengl](https://github.com/blackbearreloaded/ps5-opengl)** — GPL-3.0,
  with Mesa components retaining their own licenses. Encore pins source commit
  `ad2807d41cef2681882a9ee0d20808779f74b7cd`; `third_party/app_heap.c`
  originates from that project.

## Platform and interface

- **[PS5 Payload SDK](https://github.com/ps5-payload-dev/sdk)** — GPL-3.0.
- **[Mihawk's PS5 PayloadSDK](https://github.com/mihawk-99/PS5_PayloadSDK)** —
  GPL-3.0; fork used by the RADV/Vulkan build path.
- **[PS5 Native App Boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate)** —
  GPL-3.0. Encore reuses its native runtime, packaging integration and sandbox
  elevation helper. Its packaging code incorporates/derives work credited to
  **[SharpProspero](https://github.com/SvenGDK/SharpProspero)** — GPL-3.0.
- **[ProsperoPuzzles](https://github.com/blackbearreloaded/ProsperoPuzzles)** —
  GPL-3.0. The launcher's drawing, text, animation and sound playback code
  started from that project.
- **Montserrat** by Julieta Ulanovsky and contributors — SIL Open Font License
  1.1. The exact bundled notice is preserved under `LICENSES/`.
- **[HarfBuzz](https://github.com/harfbuzz/harfbuzz)** — its upstream COPYING
  terms. It shapes launcher text for complex scripts such as Thai and Arabic.
- **[stb](https://github.com/nothings/stb)** — upstream dual public-domain/MIT
  terms. Encore uses its font tooling/system-font support and retains upstream
  notices.
- `third_party/ps5_pad.hpp` comes from
  **[ps5-native-gamepad-input-research](https://github.com/blackbearreloaded/ps5-native-gamepad-input-research)**
  and `third_party/native_audio.hpp` from
  **[ps5-audio-decoding-research](https://github.com/blackbearreloaded/ps5-audio-decoding-research)**;
  both upstream repositories are GPL-3.0.

## Runtime metadata and media

- **[ghost-land/Nlib-API](https://github.com/ghost-land/Nlib-API)** — GPL-3.0.
  Encore queries its public NX endpoints at runtime for title metadata and
  launcher media such as icons, banners and screenshots. Nlib source code and
  a pre-seeded Nlib media library are **not** embedded in the Encore release;
  returned responses/media may be cached locally by the user.
- Copyright, trademark and other rights in metadata, cover art, banners,
  screenshots or other media returned by a remote service remain with their
  respective rightsholders. Encore does **not** represent Nlib-served media as
  public-domain, royalty-free, or licensed for independent redistribution.
  Remote-service availability and terms can change independently of Encore.

## Project-authored sound effects

The launcher UI sound files under `headless/prosperoeden/ui/sounds/` are
generated deterministically by `tools/launcher/generate-sfx.py` from
mathematical oscillators and deterministic noise. They contain no third-party
audio samples, recordings, model-generated clips, or external audio-service
output. The generation script and generated assets are distributed as part of
Encore under the project's applicable GPL-3.0-or-later terms.
## Names, logos and trademarks

Prospero.Eden Encore is an **unofficial community fork**. It is not affiliated
with, sponsored by, endorsed by, or supported by Sony Interactive
Entertainment, Nintendo, the Eden Emulator Project, or any other upstream
project unless an upstream project expressly states otherwise.

PlayStation, PS5, DualSense, Nintendo, Nintendo Switch, Eden and other product,
project or company names and logos may be trademarks or registered trademarks
of their respective owners. Their use in Encore is for attribution,
compatibility identification or description of upstream lineage and does not
imply endorsement.

Copyright licensing and trademark rights are separate. In particular,
distribution of copyrightable Eden-derived code or artwork under an applicable
open-source license does not by itself grant a right to use an owner's marks
outside the scope permitted by trademark law or separate permission.

## User-supplied console content

Encore does not include encryption keys, Nintendo firmware, commercial games,
DLC, game updates or other proprietary console content. Users must supply their
own files and are responsible for having the rights required by applicable law
for the software and data they use.

## No warranty

Encore and the third-party free/open-source software distributed with it are
provided under their respective licenses and warranty disclaimers. The GPL
warranty disclaimer for Encore is reproduced in full in [LICENSE](LICENSE).

## Thanks

ProsperoEden and Encore exist thanks to the Eden maintainers and contributors,
Mihawk, mpereiraesaa, John Törnblom, SvenGDK, the PS5 homebrew community and
the many upstream free/open-source projects credited above.
