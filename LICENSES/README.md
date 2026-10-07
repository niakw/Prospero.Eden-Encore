# Bundled third-party license texts

These files preserve license texts for direct and transitive components used to build or distribute Eden Encore.
Component-to-license provenance and distribution notes are in `../THIRD_PARTY_NOTICES.md`.
A license file being present here does not imply that every component is embedded in the final binary; build-only tools are identified in the notices.

Canonical full texts used by several entries are also preserved here: `GPL-3.0-or-later.txt`, `LGPL-2.1-or-later.txt` and `Apache-2.0.txt`. Component-specific files are kept as well because they preserve copyright notices, exceptions and project-specific wording.

The complete `LICENSES/` set from the pinned Eden commit is mirrored here as `Eden-*`, and the relevant license set plus `docs/license.rst` from the pinned Mihawk PS5 Mesa commit is mirrored as `Mesa-*`. This keeps the release self-contained even when a dependency's root `LICENSE` is only a short pointer to per-license files.

| Component | Upstream | SPDX reported by GitHub | License file |
| --- | --- | --- | --- |
| ProsperoEden | https://github.com/blackbearreloaded/ProsperoEden | `GPL-3.0` | `ProsperoEden.txt` |
| Eden | https://github.com/eden-emulator/mirror | `GPL-3.0` | `Eden.txt` |
| Dynarmic | https://github.com/lioncash/dynarmic | `0BSD` | `Dynarmic.txt` |
| Sirit | https://github.com/eden-emulator/sirit | `GPL-3.0` | `Sirit.txt` |
| PS5 OpenGL | https://github.com/blackbearreloaded/ps5-opengl | `GPL-3.0-or-later` | `PS5-OpenGL.txt` |
| FFmpeg | https://github.com/FFmpeg/FFmpeg | `NOASSERTION` | `FFmpeg.txt` |
| OpenSSL | https://github.com/openssl/openssl | `Apache-2.0` | `OpenSSL.txt` |
| zlib | https://github.com/madler/zlib | `NOASSERTION` | `zlib.txt` |
| LLVM | https://github.com/llvm/llvm-project | `NOASSERTION` | `LLVM.txt` |
| PS5-Vulkan-Mihawk | https://github.com/mihawk-99/PS5_Vulkan | `GPL-3.0` | `PS5-Vulkan-Mihawk.txt` |
| ps5-vulkan | https://github.com/mpereiraesaa/ps5-vulkan | `GPL-3.0` | `ps5-vulkan.txt` |
| PS5-Payload-SDK | https://github.com/ps5-payload-dev/sdk | `GPL-3.0` | `PS5-Payload-SDK.txt` |
| Mihawk-PS5-PayloadSDK | https://github.com/mihawk-99/PS5_PayloadSDK | `GPL-3.0` | `Mihawk-PS5-PayloadSDK.txt` |
| PS5-Native-App-Boilerplate | https://github.com/blackbearreloaded/ps5-native-app-boilerplate | `GPL-3.0` | `PS5-Native-App-Boilerplate.txt` |
| SharpProspero | https://github.com/SvenGDK/SharpProspero | `GPL-3.0` | `SharpProspero.txt` |
| ProsperoPuzzles | https://github.com/blackbearreloaded/ProsperoPuzzles | `GPL-3.0` | `ProsperoPuzzles.txt` |
| Nlib-API | https://github.com/ghost-land/Nlib-API | `GPL-3.0` | `Nlib-API.txt` |
| HarfBuzz | https://github.com/harfbuzz/harfbuzz | `NOASSERTION` | `HarfBuzz.txt` |
| stb | https://github.com/nothings/stb | `NOASSERTION` | `stb.txt` |
| PS5-Gamepad-Research | https://github.com/blackbearreloaded/ps5-native-gamepad-input-research | `GPL-3.0` | `PS5-Gamepad-Research.txt` |
| PS5-Audio-Research | https://github.com/blackbearreloaded/ps5-audio-decoding-research | `GPL-3.0` | `PS5-Audio-Research.txt` |
| fmt | https://github.com/fmtlib/fmt | `MIT` | `fmt.txt` |
| Boost | https://github.com/boostorg/boost | `BSL-1.0` | `Boost.txt` |
| Xbyak | https://github.com/herumi/xbyak | `BSD-3-Clause` | `Xbyak.txt` |
| zstd | https://github.com/facebook/zstd | `NOASSERTION` | `zstd.txt` |
| LZ4 | https://github.com/lz4/lz4 | `NOASSERTION` | `LZ4.txt` |
| Opus | https://github.com/xiph/opus | `NOASSERTION` | `Opus.txt` |
| SDL | https://github.com/libsdl-org/SDL | `Zlib` | `SDL.txt` |
| simpleini | https://github.com/brofield/simpleini | `MIT` | `simpleini.txt` |
| SPIRV-Headers | https://github.com/KhronosGroup/SPIRV-Headers | `NOASSERTION` | `SPIRV-Headers.txt` |
| Vulkan-Headers | https://github.com/KhronosGroup/Vulkan-Headers | `NOASSERTION` | `Vulkan-Headers.txt` |
| Vulkan-Utility-Libraries | https://github.com/KhronosGroup/Vulkan-Utility-Libraries | `NOASSERTION` | `Vulkan-Utility-Libraries.txt` |
| VulkanMemoryAllocator | https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator | `MIT` | `VulkanMemoryAllocator.txt` |
| ENet | https://github.com/lsalzman/enet | `MIT` | `ENet.txt` |
| frozen | https://github.com/serge-sans-paille/frozen | `Apache-2.0` | `frozen.txt` |
| cpp-httplib | https://github.com/yhirose/cpp-httplib | `MIT` | `cpp-httplib.txt` |
| nlohmann-json | https://github.com/nlohmann/json | `MIT` | `nlohmann-json.txt` |
| PSBrew-MkPFS | https://github.com/PSBrew/MkPFS | `GPL-3.0` | `PSBrew-MkPFS.txt` |

For ZBIC support, Encore compiles only the `zstd.c`/`zstd.h` implementation files from the pinned kinnay/zbic snapshot. Those files explicitly offer a BSD-style/GPLv2 choice; Encore selects the BSD-style terms preserved in `ZBIC-zstd-BSD.txt`.
