// SPDX-License-Identifier: GPL-3.0-or-later
// A game title's base control.nacp display-version, never its NSO Build ID.
// Shared by native metadata bridge and host-only C++ source regression.
#pragma once

#include <algorithm>
#include <array>
#include <cctype>
#include <cstddef>
#include <string>

namespace Eden::GlyphVersion {
template <std::size_t N>
inline std::string FromNacp(const std::array<char, N>& raw) {
    if (N == 0 || N > 64) return {};
    const auto end = std::find(raw.begin(), raw.end(), '\0');
    if (end == raw.begin()) return {};
    std::string version(raw.begin(), end);
    // Source names and catalog rules intentionally use a narrow, stable
    // ASCII subset. Unrecognized metadata must fall back to Nintendo art.
    for (unsigned char c : version)
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') || c == '.' || c == '_' ||
              c == '+' || c == '-' || c == ' ')) return {};
    return version;
}
} // namespace Eden::GlyphVersion
