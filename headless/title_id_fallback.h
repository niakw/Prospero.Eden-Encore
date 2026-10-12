// SPDX-License-Identifier: GPL-3.0-or-later
// Identical title identity in Library, Home and native game startup.
// If an NSP/XCI cannot supply metadata, an exact [16-hex-ID] filename is
// still sufficient to bind saved per-title controls and video settings.
#pragma once
#include <cstdint>
#include <string_view>

namespace Eden {

constexpr std::uint64_t TitleIdFromRomFilename(std::string_view path) noexcept {
    // A directory may contain brackets for unrelated games; only inspect
    // the actual ROM basename, including on POSIX PS5 mount paths.
    const std::size_t slash = path.find_last_of("/\\");
    const std::string_view filename = slash == std::string_view::npos
        ? path : path.substr(slash + 1);
    for (std::size_t open = filename.find('[');
         open != std::string_view::npos; open = filename.find('[', open + 1)) {
        const std::size_t close = filename.find(']', open + 1);
        if (close == std::string_view::npos || close - open != 17) continue;
        std::uint64_t value = 0;
        bool valid = true;
        for (std::size_t i = open + 1; i < close; ++i) {
            const char c = filename[i];
            unsigned digit = 0;
            if (c >= '0' && c <= '9') digit = c - '0';
            else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
            else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
            else { valid = false; break; }
            value = (value << 4) | digit;
        }
        if (valid && value != 0) return value;
    }
    return 0;
}

constexpr std::uint64_t ResolveGameTitleId(std::uint64_t metadata_id,
                                            std::string_view rom_path) noexcept {
    return metadata_id != 0 ? metadata_id : TitleIdFromRomFilename(rom_path);
}

} // namespace Eden
