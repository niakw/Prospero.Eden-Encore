#!/usr/bin/env python3
"""Per-title settings identity and controller override survive ROM metadata fallback."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / "headless/main.cpp").read_text()
scan = (ROOT / "headless/prosperoeden/eden_services.cpp").read_text()
mapping = (ROOT / "headless/button_mapping.h").read_text()
store = (ROOT / "headless/settings_store.h").read_text()
pad = (ROOT / "headless/pad.cpp").read_text()
assert 'Eden::ResolveGameTitleId(rom_metadata_id, selected_game)' in main
assert 'Eden::TitleIdFromRomFilename(file)' in scan
assert 'EDEN_TITLE_ID_LAUNCH_FALLBACK' in main
assert 'EDEN_PAD_MAPPING_FIXED' in main and 'own_mapping=%u' in main
assert 'const auto game_video = Eden::LoadGameSettings(launch_title_id);' in main
assert 'game_video.controller_layout, game_video.own_mapping, game_video.mapping' in main
assert 'pad->SetMapping(separate_fc27_gameplay ? controls.mapping : mapping);' in main
assert 'if (separate_fc27_gameplay) pad->SetGameplayMapping(fc27_gameplay_mapping);' in main
assert 'if (slots[0].handle >= 0) return;' in (ROOT / 'headless/devices.h').read_text()
assert 'const int pad = active_mapping[game];' in pad
assert 'result.own_mapping = document.contains(mapping);' in store
assert 'game["mapping"] = Settings::MappingJson(value.mapping' in store

compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
assert compiler, "C++20 compiler is required"
fixture = r"""
#include "title_id_fallback.h"
#include "button_mapping.h"
#include <cassert>
using namespace Eden;
int main() {
    constexpr auto fc27 = 0x0100C49025D3E000ULL;
    static_assert(TitleIdFromRomFilename("EA Sports FC 27 [0100C49025D3E000].nsp") == fc27);
    static_assert(TitleIdFromRomFilename("/data/roms/FC 27 [0100c49025d3e000].xci") == fc27);
    static_assert(ResolveGameTitleId(0, "/data/roms/FC 27 [0100C49025D3E000].nsp") == fc27);
    static_assert(ResolveGameTitleId(0x12345678, "/data/roms/FC 27 [0100C49025D3E000].nsp") == 0x12345678);
    static_assert(TitleIdFromRomFilename("/data/[0100C49025D3E000]/Game.nsp") == 0);
    static_assert(TitleIdFromRomFilename("Game [ZZZZZZZZZZZZZZZZ].nsp") == 0);
    static_assert(TitleIdFromRomFilename("Game [0000000000000000].nsp") == 0);
    static_assert(TitleIdFromRomFilename("Game [0100C49025D3E00].nsp") == 0);
    static_assert(TitleIdFromRomFilename("Game.nsp") == 0);
    constexpr auto inherit = ResolveSessionButtonMapping(0, kPlayStationMapping,-1,false,kSwitchMapping);
    static_assert(inherit.buttons == kPlayStationMapping);
    constexpr auto override_layout = ResolveSessionButtonMapping(0, kPlayStationMapping,1,false,kPlayStationMapping);
    static_assert(override_layout.buttons == kSwitchMapping);
    auto special = Assign(kSwitchMapping, game_a, pad_cross);
    assert(ValidMapping(special));
    const auto per_game = ResolveSessionButtonMapping(0,kPlayStationMapping,1,true,special);
    assert(per_game.buttons == special && per_game.layout == 1);
    assert(per_game.buttons != kPlayStationMapping);
    const auto independent = ResolveSessionButtonMapping(1,kSwitchMapping,0,true,kPlayStationMapping);
    assert(independent.layout == 0 && independent.buttons == kPlayStationMapping);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-ps5-title-controls-") as dirname:
    p=Path(dirname)
    source=p/"test.cpp"
    source.write_text(fixture)
    subprocess.run([compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(ROOT/"headless"),str(source),"-o",str(p/"test")],check=True,timeout=30)
    subprocess.run([str(p/"test")],check=True,timeout=15)
print("PASS PS5 title identity fallback and per-game mapping precedence, no global overwrite")
