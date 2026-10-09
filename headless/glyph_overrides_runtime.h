// SPDX-License-Identifier: GPL-3.0-or-later
// In-game PlayStation button ART, not DualSense input mapping.
// Declarative per-title catalogue, just like encore-overrides. Once at
// launch, gate an installed RomFS graphic mod against the current update.
// Unsupported/unverified versions retain Nintendo's native artwork.
#pragma once

#include <algorithm>
#include <array>
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
#include "glyph_sha256.h"

namespace Eden::GlyphOverrides {
inline constexpr std::string_view kModName = "Eden Encore PS Glyphs";
inline constexpr std::size_t kMaxCatalogBytes = 128u * 1024u;
inline constexpr std::size_t kMaxEvidenceBytes = 128u * 1024u;
inline constexpr std::uintmax_t kMaxGraphicFileBytes = 128ull * 1024 * 1024;
inline constexpr std::uintmax_t kMaxGraphicPackBytes = 512ull * 1024 * 1024;
inline constexpr bool FitsGraphicPackBudget(std::uintmax_t verified,
                                            std::uintmax_t next) noexcept {
    return verified <= kMaxGraphicPackBytes &&
           next <= kMaxGraphicFileBytes &&
           next <= kMaxGraphicPackBytes - verified;
}

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
inline bool ParseCatalogue(std::string_view text, Catalogue* output) {
    if (!output || text.empty() || text.size() > kMaxCatalogBytes) return false;
    try {
        const auto root = nlohmann::json::parse(text.begin(), text.end());
        if (!root.is_object() || root.size() != 3 ||
            !root.contains("schema_version") || !root["schema_version"].is_number_integer() ||
            root["schema_version"].get<int>() != 2 ||
            !root.contains("revision") || !root["revision"].is_number_integer() ||
            root["revision"].get<int>() < 0 ||
            !root.contains("titles") || !root["titles"].is_array() ||
            root["titles"].size() > 256) return false;
        Catalogue parsed;
        parsed.revision = root["revision"].get<int>();
        for (const auto& item : root["titles"]) {
            if (!item.is_object() || item.size() != 2 ||
                !item.contains("title_id") || !item["title_id"].is_string() ||
                !item.contains("update_version") || !item["update_version"].is_string())
                return false;
            Rule rule;
            if (!ParseHex(item["title_id"].get<std::string>(), &rule.title))
                return false;
            rule.update_version = item["update_version"].get<std::string>();
            if (rule.update_version.empty() || rule.update_version.size() > 64 ||
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
    out->clear();
    std::array<char, 4096> buffer{};
    // A pre-open file_size check alone is not a bound. The file could grow
    // after stat() (or a replace could race the open). Never use an unbounded
    // istreambuf iterator for external JSON, even on developer builds.
    for (;;) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto bytes = input.gcount();
        if (bytes < 0 || static_cast<std::size_t>(bytes) > limit - out->size()) {
            out->clear();
            return false;
        }
        if (bytes) out->append(buffer.data(), static_cast<std::size_t>(bytes));
        if (input.eof()) break;
        if (!input) {
            out->clear();
            return false;
        }
    }
    // Detect truncation/replacement while reading as well as oversize.
    const auto final_size = Mods::fs::file_size(file, ec);
    if (ec || final_size != out->size()) {
        out->clear();
        return false;
    }
    return true;
}
inline Catalogue BuiltInCatalogue() {
    Catalogue built_in;
    built_in.valid = true;
    built_in.revision = GlyphOverridesGenerated::kRevision;
    for (const auto& entry : GlyphOverridesGenerated::kRules)
        built_in.rules.push_back({entry.title, entry.update_version});
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
        remote.revision > built_in.revision) return remote;
    return built_in;
}
inline bool EvidenceMatches(const Mods::fs::path& folder, const Rule& rule) {
    std::string text;
    if (!ReadBounded(folder / "eden-glyph-pack.json", kMaxEvidenceBytes, &text))
        return false;
    try {
        const auto value = nlohmann::json::parse(text);
        if (!value.is_object() || !value.contains("schema") ||
            !value["schema"].is_number_integer() || value["schema"].get<int>() != 2 ||
            !value.contains("title_id") || !value["title_id"].is_string() ||
            !value.contains("update_version") || !value["update_version"].is_string() ||
            !value.contains("rights") || !value["rights"].is_string() ||
            value["rights"].get<std::string>().empty() ||
            !value.contains("files") || !value["files"].is_array() ||
            value["files"].empty() || value["files"].size() > 64)
            return false;
        std::uint64_t evidence_title = 0;
        if (!ParseHex(value["title_id"].get<std::string>(), &evidence_title) ||
            evidence_title != rule.title ||
            value["update_version"].get<std::string>() != rule.update_version)
            return false;
        // Installer checks ORIGINAL RomFS bytes at packaging; launch checks
        // each replacement asset byte-for-byte via SHA-256. The original
        // file currently mounted by the emulator is still a separate gate.
        // Match the 512 MiB aggregate installer cap, not only the 128 MiB
        // per-file cap: otherwise an edited 64-file manifest could force
        // gigabytes of filesystem reads and freeze the game-launch path.
        std::uintmax_t verified_bytes = 0;
        // LayeredFS path names must be unambiguous regardless of a target
        // filesystem's case sensitivity. Two manifest rows for the same
        // lowercased path (or a file also acting as a parent directory)
        // could pass individual SHA checks but resolve to different bytes
        // depending on extraction order or host OS.
        std::vector<std::string> claimed_romfs_paths;
        for (const auto& item : value["files"]) {
            if (!item.is_object() || !item.contains("romfs_path") ||
                !item["romfs_path"].is_string() ||
                !item.contains("original_sha256") || !item["original_sha256"].is_string() ||
                !item.contains("replacement_sha256") || !item["replacement_sha256"].is_string()) return false;
            // Evidence must still be a file-hash-verified pack generated by
            // the installer. Valid declarations alone do NOT attest the
            // currently decrypted original RomFS on hardware.
            const auto hash_ok = [](const std::string& hash) {
                return hash.size() == 64 && std::all_of(hash.begin(), hash.end(),
                    [](unsigned char c) {
                        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
                               (c >= 'A' && c <= 'F');
                    });
            };
            if (!hash_ok(item["original_sha256"].get<std::string>()) ||
                !hash_ok(item["replacement_sha256"].get<std::string>()))
                return false;
            const std::string relative = item["romfs_path"].get<std::string>();
            if (relative.empty() || relative.size() > 240 ||
                relative.front() == '/' || relative.find('\\') != std::string::npos ||
                relative.find(':') != std::string::npos) return false;
            Mods::fs::path safe;
            for (const auto& segment : Mods::fs::path(relative)) {
                if (segment == "." || segment == ".." || segment.empty()) return false;
                safe /= segment;
            }
            // Refuse aliases via doubled separators, dot segments or
            // host-dependent path normalization before checking file hashes.
            if (safe.generic_string() != relative) return false;
            const std::string folded = Mods::Lower(relative);
            for (const auto& prior : claimed_romfs_paths) {
                if (folded == prior ||
                    (folded.size() > prior.size() &&
                     folded.compare(0, prior.size(), prior) == 0 &&
                     folded[prior.size()] == '/') ||
                    (prior.size() > folded.size() &&
                     prior.compare(0, folded.size(), folded) == 0 &&
                     prior[folded.size()] == '/'))
                    return false;
            }
            claimed_romfs_paths.push_back(folded);
            // Reject symlinks in any component, not only at the leaf.
            // These graphics are injected into the guest's RomFS and must
            // not escape the installed pack or point to executable mods.
            Mods::fs::path asset = folder / "romfs";
            std::error_code ec;
            if (Mods::fs::is_symlink(asset, ec) || ec) return false;
            for (const auto& part : safe) {
                asset /= part;
                if (Mods::fs::is_symlink(asset, ec) || ec) return false;
            }
            if (!Mods::fs::is_regular_file(asset, ec) || ec) return false;
            const auto bytes = Mods::fs::file_size(asset, ec);
            if (ec || !FitsGraphicPackBudget(verified_bytes, bytes)) return false;
            verified_bytes += bytes;
            const auto actual = GlyphIntegrity::FileSha256(asset, kMaxGraphicFileBytes);
            std::string expected = item["replacement_sha256"].get<std::string>();
            std::transform(expected.begin(), expected.end(), expected.begin(),
                           [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            // The previous check only ensured *presence* of artwork; an
            // altered atlas with the same filename was silently admitted.
            // Hash the replacement once during launch before loading RomFS.
            if (!actual || *actual != expected) return false;
        }
        return true;
    } catch (...) { return false; }
}
// Version discovery can decrypt/open a game container to inspect NACP.
// Never do it for games without a published rule, absent graphic mods,
// or when PlayStation art is disabled. Especially important when the
// shared catalogue is empty: no all-library metadata penalty at all.
inline bool NeedsGameVersion(const Catalogue& catalogue, std::uint64_t title,
                             Style style, const std::vector<Mods::Mod>& mods) {
    if (!catalogue.valid || style == Style::Nintendo) return false;
    const bool candidate = std::any_of(catalogue.rules.begin(), catalogue.rules.end(),
        [&](const Rule& rule) { return rule.title == title; });
    if (!candidate) return false;
    return std::any_of(mods.begin(), mods.end(), [](const Mods::Mod& mod) {
        return Mods::Lower(mod.name) == Mods::Lower(kModName) && (mod.kinds & Mods::kFiles);
    });
}
inline State Select(const Catalogue& catalogue, std::uint64_t title,
                    std::string_view running_update_version, Style style,
                    const std::string& mods_root, const std::vector<Mods::Mod>& mods) {
    if (style == Style::Nintendo) return State::Disabled;
    if (!catalogue.valid) return State::Unsupported;
    const auto it = std::find_if(catalogue.rules.begin(), catalogue.rules.end(),
                                 [&](const Rule& rule) { return rule.title == title; });
    if (it == catalogue.rules.end()) return State::Unsupported;
    // Eden mod discovery is case-insensitive for titles but not for mod
    // payload order. Two visually identical mod names differing by case
    // can be applied together, with ambiguous graphic replacement order.
    const auto matching = [](const Mods::Mod& entry) {
        return Mods::Lower(entry.name) == Mods::Lower(kModName);
    };
    const auto count = std::count_if(mods.begin(), mods.end(), matching);
    if (count == 0) return State::MissingMod;
    if (count != 1) return State::EvidenceMismatch;
    const auto mod = std::find_if(mods.begin(), mods.end(), matching);
    if (mod->name != kModName || !(mod->kinds & Mods::kFiles))
        return State::EvidenceMismatch;
    if (running_update_version.empty()) return State::UnknownVersion;
    const auto rule = std::find_if(catalogue.rules.begin(), catalogue.rules.end(),
                                   [&](const Rule& r) {
                                       return r.title == title && r.update_version == running_update_version;
                                   });
    if (rule == catalogue.rules.end()) return State::VersionMismatch;
    // The ordinary mod loader chooses the first case-insensitive title
    // directory it encounters. Two folders with the same logical Title ID
    // can change which RomFS wins between filesystem enumerations. Require
    // exactly one unambiguous physical title folder for verified artwork.
    const std::string wanted_title = Mods::Lower(Mods::TitleName(title));
    unsigned title_folders = 0;
    for (const auto& entry : Mods::ListFolder(mods_root)) {
        if (Mods::Lower(entry.path().filename().string()) != wanted_title) continue;
        std::error_code symlink_error;
        if (!Mods::IsFolder(entry) ||
            Mods::fs::is_symlink(entry.path(), symlink_error) || symlink_error ||
            ++title_folders > 1) return State::EvidenceMismatch;
    }
    if (title_folders != 1) return State::EvidenceMismatch;
    const auto root = Mods::TitleFolder(mods_root, title);
    if (root.empty()) return State::EvidenceMismatch;
    const auto title_folder = Mods::fs::path(root);
    const auto pack_folder = title_folder / std::string(kModName);
    std::error_code ec;
    if (Mods::fs::is_symlink(title_folder, ec) || ec ||
        Mods::fs::is_symlink(pack_folder, ec) || ec ||
        !EvidenceMatches(pack_folder, *rule))
        return State::EvidenceMismatch;
    return State::Enabled;
}
} // namespace Eden::GlyphOverrides
