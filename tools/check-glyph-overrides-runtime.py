#!/usr/bin/env python3
"""Compile *actual* in-game glyph override selector and preference persistence.

Host-only C++20 with nlohmann/json.hpp; never builds the PS5 app or GUI.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CXX = next((item for item in ("clang++-18", "clang++", "g++") if shutil.which(item)), None)
if not CXX:
    raise SystemExit("missing host C++20 compiler")
TEST = r"""
#include "glyph_overrides_runtime.h"
#include "settings_store.h"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using Eden::GlyphOverrides::Catalogue;
using Eden::GlyphOverrides::State;
using Eden::GlyphOverrides::Style;
static constexpr std::uint64_t GAME = 0x0100C49025D3E000ull;

void put(const fs::path& path, const std::string& value) {
    fs::create_directories(path.parent_path());
    std::ofstream out(path);
    assert(bool(out));
    out << value;
}
std::string catalogue(std::string_view version = "v1.2.0") {
    return R"({"schema_version":1,"revision":7,"titles":[{"title_id":"0100C49025D3E000","update_version":")"
        + std::string(version) + R"(","build_id":"0123456789ABCDEF0123456789ABCDEF01234567"}]})";
}
const std::string evidence = R"({"schema":1,"title_id":"0100C49025D3E000",
    "build_id":"0123456789ABCDEF0123456789ABCDEF01234567",
    "rights":"Original artist-owned PlayStation art",
    "files":[{"romfs_path":"ui/controller.bntx",
              "replacement":"files/controller.bntx",
              "original_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              "replacement_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}]})";
int main(int argc, char** argv) {
    assert(argc == 2);
    const fs::path base = argv[1];
    const fs::path mods = base / "mods";
    const fs::path title = mods / "0100c49025d3e000"; // existing LOWERCASE
    const fs::path pack = title / "Eden Encore PS Glyphs";
    const fs::path catalogue_path = base / "encore-glyph-overrides.json";
    const fs::path preferences = base / "prosperoeden.json";
    put(pack / "romfs" / "ui" / "controller.bntx", "synthetic user-owned PS atlas");
    put(pack / "eden-glyph-pack.json", evidence);
    put(catalogue_path, catalogue());
    Catalogue data = Eden::GlyphOverrides::LoadCatalogue(catalogue_path);
    assert(data.valid && data.revision == 7 && data.rules.size() == 1);
    auto mods_found = Eden::Mods::List(mods.string(), GAME);
    assert(mods_found.size() == 1 &&
           mods_found[0].name == "Eden Encore PS Glyphs" &&
           (mods_found[0].kinds & Eden::Mods::kFiles));
    const auto select = [&](const Catalogue& cat, std::string_view version, Style style) {
        return Eden::GlyphOverrides::Select(cat, GAME, version, style,
                                            mods.string(), mods_found);
    };
    assert(select(data, "v1.2.0", Style::PlayStation) == State::Enabled);
    assert(select(data, "v1.2.0", Style::Nintendo) == State::Disabled);
    assert(select(data, "", Style::PlayStation) == State::UnknownVersion);
    assert(select(data, "v1.2.1", Style::PlayStation) == State::VersionMismatch);
    assert(Eden::GlyphOverrides::Select(data, 0x0100DEAD00000000ull, "v1.2.0",
           Style::PlayStation, mods.string(), {}) == State::Unsupported);
    assert(Eden::GlyphOverrides::Select(data, GAME, "v1.2.0",
           Style::PlayStation, mods.string(), {}) == State::MissingMod);
    auto unknown = data;
    unknown.valid = false;
    assert(select(unknown, "v1.2.0", Style::PlayStation) == State::Unsupported);

    auto rejected = [&](const std::string& body) {
        Catalogue bad;
        assert(!Eden::GlyphOverrides::ParseCatalogue(body, &bad));
    };
    rejected(R"({"schema_version":2,"revision":7,"titles":[]})");
    rejected(R"({"schema_version":1,"revision":7,"titles":[
      {"title_id":"NOTHEX","update_version":"v1","build_id":"123"}]})");
    rejected(R"({"schema_version":1,"revision":7,"titles":[
      {"title_id":"0100C49025D3E000","update_version":"v1",
       "build_id":"0123456789ABCDEF0123456789ABCDEF01234567"},
      {"title_id":"0100C49025D3E000","update_version":"v1",
       "build_id":"0123456789ABCDEF0123456789ABCDEF01234567"}]})");

    // Correct game ID but a tampered / missing pack is NOT admitted.
    put(pack / "eden-glyph-pack.json",
        R"({"schema":1,"title_id":"0100DEAD00000000","build_id":"0123456789ABCDEF0123456789ABCDEF01234567","rights":"ok","files":[{"romfs_path":"ui/controller.bntx"}]})");
    assert(select(data, "v1.2.0", Style::PlayStation) == State::EvidenceMismatch);
    put(pack / "eden-glyph-pack.json", evidence);
    fs::remove(pack / "romfs" / "ui" / "controller.bntx");
    assert(select(data, "v1.2.0", Style::PlayStation) == State::EvidenceMismatch);
    put(pack / "romfs" / "ui" / "controller.bntx", "restored synthetic PS atlas");
    assert(select(data, "v1.2.0", Style::PlayStation) == State::Enabled);

    // Stored artist preference never silently modifies effective button mapping.
    assert(Eden::LoadInGamePlayStationGlyphs(GAME, preferences.string()));
    const auto original_mapping = Eden::LoadPreferences(preferences.string()).mapping;
    assert(Eden::SaveInGameButtonGlyphs(0, false, preferences.string()));
    assert(!Eden::LoadInGamePlayStationGlyphs(GAME, preferences.string()));
    assert(Eden::SaveInGameButtonGlyphs(GAME, true, preferences.string()));
    assert(Eden::LoadInGamePlayStationGlyphs(GAME, preferences.string()));
    assert(!Eden::LoadInGamePlayStationGlyphs(0x0100DEAD00000000ull, preferences.string()));
    assert(Eden::SaveInGameButtonGlyphs(GAME, false, preferences.string()));
    assert(!Eden::LoadInGamePlayStationGlyphs(GAME, preferences.string()));
    assert(Eden::LoadPreferences(preferences.string()).mapping == original_mapping);

    std::cout << "PASS real C++ in-game glyph override catalogue: title/update gate, separate artwork style, disabled original fallback, mod/evidence safety\n";
}
""";
with tempfile.TemporaryDirectory(prefix="eden-glyph-override-runtime-") as temp:
    root = Path(temp)
    source = root / "glyph_override_check.cpp"
    exe = root / "glyph_override_check"
    source.write_text(TEST)
    subprocess.run([CXX, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "headless"), str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe), str(root / "fixtures")], check=True)

print("IN-GAME button art: only source mock catalogue; no PS5 glyph resources rendered")
