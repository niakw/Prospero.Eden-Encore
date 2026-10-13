#!/usr/bin/env python3
"""R448: FC27 per-title match buttons cannot override global PlayStation menus."""
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
pad=(root/"headless/pad.cpp").read_text()
device=(root/"headless/devices.h").read_text()
main=(root/"headless/main.cpp").read_text()
ui=(root/"headless/prosperoeden/pe/ui/mapping.cpp").read_text()
store=(root/"headless/settings_store.h").read_text()
assert "separate_fc27_gameplay = Eden::HasFc27MatchMapping(" in main
assert "pad->SetMapping(separate_fc27_gameplay ? controls.mapping : mapping);" in main
assert "if (separate_fc27_gameplay) pad->SetGameplayMapping(mapping);" in main
assert "mode=dual_manual gesture=touchpad_square" in main
assert "void SetGameplayMapping(const ButtonMapping& value)" in device
assert "has_gameplay_mapping && gameplay_mode ? gameplay_mapping : mapping" in device
assert "constexpr ButtonMask gameplay_chord = kButtonTouchPad | kButtonSquare;" in pad
assert "if (gameplay_chord_down && !slot.gameplay_chord_held)" in pad
assert "slot.gameplay_chord_held = gameplay_chord_down;" in pad
assert "sample.buttons &= ~(kButtonTouchPad | kButtonSquare);" in pad
assert "EDEN_PAD_GAMEPLAY_PROFILE mode=%s" in pad
assert "const int pad = active_mapping[game];" in pad
assert "MappedTo(ActiveMapping(), pad_touchpad)" in pad
assert "MappedTo(active_mapping, pad_create)" in pad
assert "next.own_mapping = true;" in ui and "next.mapping = mapping;" in ui
assert 'game["mapping"] = Settings::MappingJson(value.mapping' in store
assert "mapping_context.observe(" not in pad
cpp=r"""
#include "button_mapping.h"
#include <cassert>
using namespace Eden;
int main() {
    auto custom=Assign(kPlayStationMapping,game_a,pad_circle);
    assert(custom[game_a]==pad_circle && custom[game_b]==pad_cross);
    static_assert(!HasFc27MatchMapping(kFc27TitleId,false,kPlayStationMapping,kSwitchMapping));
    static_assert(!HasFc27MatchMapping(0x01007EF00011E000ULL,true,kPlayStationMapping,kSwitchMapping));
    static_assert(!HasFc27MatchMapping(kFc27TitleId,true,kPlayStationMapping,kPlayStationMapping));
    assert(HasFc27MatchMapping(kFc27TitleId,true,kPlayStationMapping,custom));
    auto selected=ResolveSessionButtonMapping(0,kPlayStationMapping,0,true,custom);
    assert(selected.buttons==custom);
    assert(kPlayStationMapping[game_a]==pad_cross);
    assert(ValidMapping(selected.buttons));
}
"""
cxx=next((x for x in ("clang++-18","clang++","g++") if shutil.which(x)),None)
assert cxx
with tempfile.TemporaryDirectory(prefix="eden-fc27-dual-") as d:
    src=Path(d)/"test.cpp";exe=Path(d)/"test";src.write_text(cpp)
    subprocess.run([cxx,"-std=c++20","-Wall","-Wextra","-Werror","-I",str(root/"headless"),str(src),"-o",str(exe)],check=True,timeout=60)
    subprocess.run([str(exe)],check=True,timeout=20)
print("R448 FC27 dual physical mapping source and C++ title resolver PASS")
