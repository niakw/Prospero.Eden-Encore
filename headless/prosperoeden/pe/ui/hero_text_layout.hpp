// SPDX-License-Identifier: GPL-3.0-or-later
// Pure, host-testable Hero synopsis layout. No PS5/graphics/locale dependencies.
#pragma once
#include <algorithm>
#include <array>
#include <cctype>
#include <string>
#include <string_view>
#include <vector>

namespace pe::ui::hero_text {

struct Layout {
    std::vector<std::string> lines;
    bool truncated = false;
};

// Nlib sometimes supplies line breaks and whitespace in a long synopsis.
// They are paragraph formatting, not separate UI lines.
inline std::vector<std::string> words(std::string_view source) {
    std::vector<std::string> result;
    std::size_t pos = 0;
    while (pos < source.size()) {
        while (pos < source.size() &&
               std::isspace(static_cast<unsigned char>(source[pos]))) ++pos;
        const std::size_t begin = pos;
        while (pos < source.size() &&
               !std::isspace(static_cast<unsigned char>(source[pos]))) ++pos;
        if (pos > begin) result.emplace_back(source.substr(begin, pos - begin));
    }
    // An API-supplied final standalone ellipsis is not a second sentence.
    while (!result.empty() && (result.back() == "..." || result.back() == "…"))
        result.pop_back();
    return result;
}

inline bool weak_ending(std::string_view word) {
    constexpr std::array<std::string_view, 65> weak{
        "a", "à", "au", "aux", "avec", "ce", "ces", "cet", "cette",
        "dans", "de", "des", "du", "elle", "elles", "en", "et", "il",
        "ils", "je", "la", "le", "les", "leur", "leurs", "lui", "mais",
        "mes", "mon", "ne", "nos", "notre", "nous", "ou", "où", "par",
        "pour", "que", "qui", "sa", "se", "ses", "son", "sur", "ta",
        "te", "tes", "ton", "tu", "un", "une", "vous", "y",
        "an", "and", "at", "by", "for", "from", "in", "of", "or",
        "the", "to", "with"
    };
    std::string lowered(word);
    for (char& c : lowered)
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c + ('a' - 'A'));
    return std::find(weak.begin(), weak.end(), lowered) != weak.end();
}

inline void drop_end_punctuation(std::string& line) {
    while (!line.empty() && (line.back() == ',' || line.back() == ';' ||
           line.back() == ':' || line.back() == '.' || line.back() == '!' ||
           line.back() == ' ' || line.back() == '\t')) line.pop_back();
}

// Measure(text, font_size) must call the SAME font as the real renderer.
// A partial word never counts as a meaningful ending.
template <class Measure>
Layout wrap_description(std::string_view text, float font_size, float max_width,
                        int max_lines, Measure measure) {
    Layout out;
    if (max_width <= 0.0f || max_lines <= 0 || font_size <= 0.0f) return out;
    const auto terms = words(text);
    if (terms.empty()) return out;
    std::size_t next = 0;
    for (int row = 0; row < max_lines && next < terms.size(); ++row) {
        std::string line;
        while (next < terms.size()) {
            const std::string candidate = line.empty() ? terms[next] :
                line + " " + terms[next];
            if (!line.empty() && measure(candidate, font_size) > max_width)
                break;
            line = candidate;
            ++next;
        }
        if (line.empty()) break;
        out.lines.push_back(std::move(line));
    }
    out.truncated = next < terms.size();
    if (!out.truncated || out.lines.empty()) return out;

    // The visible suffix is reserved in font pixels, on the last meaningful
    // complete word. Never produce a second line containing only dots.
    for (;;) {
        std::string& line = out.lines.back();
        while (!line.empty()) {
            drop_end_punctuation(line);
            if (line.empty()) break;
            const auto boundary = line.find_last_of(' ');
            const std::string_view last(line.data() +
                (boundary == std::string::npos ? 0 : boundary + 1),
                line.size() - (boundary == std::string::npos ? 0 : boundary + 1));
            const std::string candidate = line + " ...";
            if (!weak_ending(last) && measure(candidate, font_size) <= max_width) {
                line = candidate;
                return out;
            }
            if (boundary == std::string::npos) break;
            line.erase(boundary);
        }
        out.lines.pop_back();
        if (out.lines.empty()) return out; // no isolated ellipsis ever
    }
}

} // namespace pe::ui::hero_text
