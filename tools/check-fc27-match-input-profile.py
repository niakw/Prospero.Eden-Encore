#!/usr/bin/env python3
"""Native host contract: guest-saved action bindings never receive title-specific swaps."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pad = (root / "headless/pad.cpp").read_text()
device = (root / "headless/devices.h").read_text()
main = (root / "headless/main.cpp").read_text()
ui = (root / "headless/prosperoeden/pe/ui/mapping.cpp").read_text()
store = (root / "headless/settings_store.h").read_text()
mapping_header = (root / "headless/button_mapping.h").read_text()

assert "pad->SetMapping(mapping);" in main
assert main.index("pad->SetMapping(mapping);") < main.index("if (!pad->Open())")
assert "SetGameplayMapping" not in main + device + pad
assert "Fc27GameplayButtons" not in main + mapping_header
assert "HasFc27MatchMapping" not in main + mapping_header
assert "has_gameplay_mapping" not in device + pad
assert "gameplay_mode" not in device + pad
assert "gameplay_chord" not in device + pad
assert "EDEN_PAD_GAMEPLAY_PROFILE" not in pad
assert "EDEN_PAD_MAPPING_LOCKED scope=session mode=static game_actions=guest_owned" in main
assert "EDEN_PAD_MAPPING_CONTEXT title=%016llx mode=game_owned" in main
assert "const int pad = active_mapping[game];" in pad
assert "MappedTo(ActiveMapping(), pad_touchpad)" in pad
assert "MappedTo(active_mapping, pad_create)" in pad
assert "next.own_mapping = true;" in ui and "next.mapping = mapping;" in ui
assert 'game["mapping"] = Settings::MappingJson(value.mapping' in store
assert "mapping_context.observe(" not in pad

cpp = r"""
#include "button_mapping.h"
#include <cassert>
using namespace Eden;
int main() {
    // Both physical and title-specific launcher profiles resolve exactly once.
    const auto globally_selected = ResolveSessionButtonMapping(
        0, kPlayStationMapping, -1, false, kPlayStationMapping);
    assert(globally_selected.buttons == kPlayStationMapping);
    const auto custom = Assign(kPlayStationMapping, game_a, pad_circle);
    const auto title_selected = ResolveSessionButtonMapping(
        0, kPlayStationMapping, 0, true, custom);
    assert(title_selected.buttons == custom);
    assert(ValidMapping(title_selected.buttons));
    assert(title_selected.buttons[game_a] == pad_circle);
    assert(globally_selected.buttons[game_a] == pad_cross);
    // Guest action settings are not stored or inferred by this resolver.
}
"""
cxx = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
assert cxx, "C++20 compiler required for controller regression"
with tempfile.TemporaryDirectory(prefix="encore-guest-actions-") as folder:
    src = Path(folder) / "test.cpp"
    exe = Path(folder) / "test"
    src.write_text(cpp)
    subprocess.run([cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root / "headless"), str(src), "-o", str(exe)],
                   check=True, timeout=60)
    subprocess.run([str(exe)], check=True, timeout=20)
print("PASS: one stable controller mapping, no match/pause override of guest action bindings")
print("Guest save-file persistence and on-device gameplay remain hardware test gates")
