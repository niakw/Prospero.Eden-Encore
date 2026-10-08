// SPDX-License-Identifier: GPL-3.0-or-later
// In-game PlayStation button ART, not DualSense input mapping.
// Declarative per-title catalogue, just like encore-overrides. Once at
// launch, gate an installed RomFS graphic mod against the current update.
// Unsupported/unverified versions retain Nintendo's native artwork.
#pragma once

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include "mods.h"
#include "glyph_overrides_generated.h"

namespace Eden::GlyphOverrides {
inline constexpr std::string_view kModName = "Eden Encore PS Glyphs";
inline constexpr std::size_t kMaxCatalogBytes = 128u * 1024u;
inline constexpr std::size_t kMaxEvidenceBytes = 128u * 1024u;

enum class Style { PlayStation, Nintendo };
enum class State { Unsupported, Disabled, MissingMod, UnknownVersion, VersionMismatch,
                   EvidenceMismatch, Enabled };
inline const char* StateName(State state) noexcept {
    switch (state) {
    case State::Unsupported: return "unsupported";
    case State::Disabled: return "nintendo_selected";
    case State::MissingMod: return "mod_missing";
    case State::UnknownVersion: return "update_version_unknown";
    case State::VersionMismatch: return "update_version_mismatch";
    case State::EvidenceMismatch: return "pack_evidence_mismatch";
    case State::Enabled: return "playstation_art_active";
    }
    return "invalid";
}
struct Rule {
    std::uint64_t title = 0;
    std::string update_version;
    std::string build_id;
};
struct Catalogue {
    bool valid = false;
    int revision = 0;
    std::vector<Rule> rules;
};
inline bool ParseHex(std::string_view input, std::uint64_t* value) noexcept {
    if (!value || input.size() != 16) return false;
    std::uint64_t parsed = 0;
    for (unsigned char c : input) {
        unsigned digit = 0;
        if (c >= '0' && c <= '9') digit = c - '0';
        else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
        else return false;
        parsed = (parsed << 4) | digit;
    }
    *value = parsed;
    return parsed != 0;
}
inline bool HexBuild(std::string_view input) noexcept {
    if (input.size() != 40 && input.size() != 64) return false;
    return std::all_of(input.begin(), input.end(), [](unsigned char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
               (c >= 'A' && c <= 'F');
    });
}
inline std::string Upper(std::string text) {
    for (auto& c : text) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return text;
}
inline bool ParseCatalogue(std::string_view text, Catalogue* output) {
    if (!output || text.empty() || text.size() > kMaxCatalogBytes) return false;
    try {
        const auto root = nlohmann::json::parse(text.begin(), text.end());
        if (!root.is_object() || root.size() != 3 ||
            !root.contains("schema_version") || !root["schema_version"].is_number_integer() ||
            root["schema_version"].get<int>() != 1 ||
            !root.contains("revision") || !root["revision"].is_number_integer() ||
            root["revision"].get<int>() < 0 ||
            !root.contains("titles") || !root["titles"].is_array() ||
            root["titles"].size() > 256) return false;
        Catalogue parsed;
        parsed.revision = root["revision"].get<int>();
        for (const auto& item : root["titles"]) {
            if (!item.is_object() || item.size() != 3 ||
                !item.contains("title_id") || !item["title_id"].is_string() ||
                !item.contains("update_version") || !item["update_version"].is_string() ||
                !item.contains("build_id") || !item["build_id"].is_string())
                return false;
            Rule rule;
            if (!ParseHex(item["title_id"].get<std::string>(), &rule.title))
                return false;
            rule.update_version = item["update_version"].get<std::string>();
            rule.build_id = Upper(item["build_id"].get<std::string>());
            if (rule.update_version.empty() || rule.update_version.size() > 64 ||
                !HexBuild(rule.build_id) ||
                std::any_of(rule.update_version.begin(), rule.update_version.end(), [](unsigned char c) {
                    return c < 32 || c == 127;
                })) return false;
            // One build per title+display-version: ambiguities fail closed.
            if (std::any_of(parsed.rules.begin(), parsed.rules.end(), [&](const Rule& old) {
                    return old.title == rule.title && old.update_version == rule.update_version;
                })) return false;
            parsed.rules.push_back(std::move(rule));
        }
        parsed.valid = true;
        *output = std::move(parsed);
        return true;
    } catch (...) { return false; }
}
inline bool ReadBounded(const Mods::fs::path& file, std::size_t limit, std::string* out) {
    if (!out) return false;
    std::error_code ec;
    if (Mods::fs::is_symlink(file, ec) || ec ||
        !Mods::fs::is_regular_file(file, ec) || ec ||
        Mods::fs::file_size(file, ec) > limit || ec) return false;
    std::ifstream input(file, std::ios::binary);
    if (!input) return false;
    out->assign(std::istreambuf_iterator<char>(input), {});
    return input.eof() || (input.good() && out->size() <= limit);
}
inline Catalogue BuiltInCatalogue() {
    Catalogue built_in;
    built_in.valid = true;
    built_in.revision = GlyphOverridesGenerated::kRevision;
    for (const auto& entry : GlyphOverridesGenerated::kRules)
        built_in.rules.push_back({entry.title, entry.update_version, entry.build_id});
    return built_in;
}
inline Catalogue LoadCatalogue(const Mods::fs::path& path) {
    Catalogue built_in = BuiltInCatalogue();
    std::string content;
    Catalogue remote;
    // Runtime updates may add support, never silently downgrade the embedded
    // source snapshot (same model as encore-overrides video profiles).
    if (ReadBounded(path, kMaxCatalogBytes, &content) &&
        ParseCatalogue(content, &remote) &&
        remote.revision >= built_in.revision) return remote;
    return built_in;
}
inline bool EvidenceMatches(const Mods::fs::path& folder, const Rule& rule) {
    std::string text;
    if (!ReadBounded(folder / "eden-glyph-pack.json", kMaxEvidenceBytes, &text))
        return false;
    try {
        const auto value = nlohmann::json::parse(text);
        if (!value.is_object() || !value.contains("schema") ||
            !value["schema"].is_number_integer() || value["schema"].get<int>() != 1 ||
            !value.contains("title_id") || !value["title_id"].is_string() ||
            !value.contains("build_id") || !value["build_id"].is_string() ||
            !value.contains("rights") || !value["rights"].is_string() ||
            value["rights"].get<std::string>().empty() ||
            !value.contains("files") || !value["files"].is_array() ||
            value["files"].empty() || value["files"].size() > 64)
            return false;
        std::uint64_t evidence_title = 0;
        if (!ParseHex(value["title_id"].get<std::string>(), &evidence_title) ||
            evidence_title != rule.title ||
            Upper(value["build_id"].get<std::string>()) != rule.build_id)
            return false;
        // Install writes hash-verified graphics into the real RomFS mod dir.
        // Check their declared paths still exist; do not trust a stale marker.
        for (const auto& item : value["files"]) {
            if (!item.is_object() || !item.contains("romfs_path") ||
                !item["romfs_path"].is_string()) return false;
            const std::string relative = item["romfs_path"].get<std::string>();
            if (relative.empty() || relative.size() > 240 ||
                relative.front() == '/' || relative.find('\\') != std::string::npos ||
                relative.find(':') != std::string::npos) return false;
            Mods::fs::path safe;
            for (const auto& segment : Mods::fs::path(relative)) {
                if (segment == "." || segment == ".." || segment.empty()) return false;
                safe /= segment;
            }
            const Mods::fs::path asset = folder / "romfs" / safe;
            std::error_code ec;
            if (Mods::fs::is_symlink(asset, ec) || ec ||
                !Mods::fs::is_regular_file(asset, ec) || ec) return false;
        }
        return true;
    } catch (...) { return false; }
}
inline State Select(const Catalogue& catalogue, std::uint64_t title,
                    std::string_view running_update_version, Style style,
                    const std::string& mods_root, const std::vector<Mods::Mod>& mods) {
    if (style == Style::Nintendo) return State::Disabled;
    if (!catalogue.valid) return State::Unsupported;
    const auto it = std::find_if(catalogue.rules.begin(), catalogue.rules.end(),
                                 [&](const Rule& rule) { return rule.title == title; });
    if (it == catalogue.rules.end()) return State::Unsupported;
    const auto mod = std::find_if(mods.begin(), mods.end(), [](const Mods::Mod& entry) {
        return entry.name == kModName && (entry.kinds & Mods::kFiles);
    });
    if (mod == mods.end()) return State::MissingMod;
    if (running_update_version.empty()) return State::UnknownVersion;
    const auto rule = std::find_if(catalogue.rules.begin(), catalogue.rules.end(),
                                   [&](const Rule& r) {
                                       return r.title == title && r.update_version == running_update_version;
                                   });
    if (rule == catalogue.rules.end()) return State::VersionMismatch;
    const auto root = Mods::TitleFolder(mods_root, title);
    if (root.empty() || !EvidenceMatches(Mods::fs::path(root) / std::string(kModName), *rule))
        return State::EvidenceMismatch;
    return State::Enabled;
}
} // namespace Eden::GlyphOverrides
