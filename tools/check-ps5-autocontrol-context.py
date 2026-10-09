#!/usr/bin/env python3
"""PS5 game input: host regression for immutable, prelaunch controller mapping.

The title's HID stream does NOT expose a reliable menu/match semantic event.
Like PC emulators, resolve global/title preferences before boot and keep the
guest A/B/X/Y mapping unchanged for the entire session. This test is staged
but MUST NOT be executed until the user authorizes a CI run.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
pad = (ROOT / "headless/pad.cpp").read_text()
device = (ROOT / "headless/devices.h").read_text()
launcher = (ROOT / "headless/main.cpp").read_text()
ui = (ROOT / "headless/prosperoeden/pe/ui/mapping.cpp").read_text()
mapper = (ROOT / "headless/button_mapping.h").read_text()
assert 'ResolveSessionButtonMapping(' in mapper
assert "Eden::ResolveSessionButtonMapping(" in launcher
assert "ResolveSessionButtonMapping(" in ui
assert 'pad->SetMapping(mapping);' in launcher
assert 'pad->SetMapping(mapping);' in launcher.split('pad->Open()', 1)[0]
assert 'EDEN_PAD_MAPPING_LOCKED scope=session mode=static' in launcher
assert 'void SetMapping(const ButtonMapping& value)' in device
assert 'if (slots[0].handle >= 0) return;' in device
assert 'SetAdaptivePlayStation' not in device
assert 'SetAdaptivePlayStation' not in launcher
assert 'mapping_context' not in pad and 'mapping_context' not in device
assert 'adaptive_playstation' not in pad
assert 'manual_toggle' not in pad
assert 'layout_chord' not in pad
assert 'const int pad = mapping[game];' in pad
assert 'MappedTo(mapping, pad_touchpad);' in pad
assert 'MappedTo(mapping, pad_create) < 0;' in pad
assert 'constexpr ButtonMask menu_chord = kButtonTouchPad | kButtonL1;' in pad
assert 'constexpr ButtonMask hud_chord = kButtonTouchPad | kButtonR1;' in pad

compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if compiler is None:
    raise SystemExit("C++20 compiler required")
fixture = r"""
#include "button_mapping.h"
#include <cassert>
using namespace Eden;
int main() {
    // Global layout is applied before boot and cannot be replaced by input
    // activity: the resolver doesn't even accept gameplay/menu signals.
    constexpr auto inherited = ResolveSessionButtonMapping(
        0, kPlayStationMapping, -1, false, kSwitchMapping);
    static_assert(inherited.layout == 0 && inherited.buttons == kPlayStationMapping);
    constexpr auto game_layout = ResolveSessionButtonMapping(
        0, kPlayStationMapping, 1, false, kPlayStationMapping);
    static_assert(game_layout.layout == 1 && game_layout.buttons == kSwitchMapping);
    // One game overrides the global profile without a custom mapping.
    constexpr auto game_ps = ResolveSessionButtonMapping(
        1, kSwitchMapping, 0, false, kSwitchMapping);
    static_assert(game_ps.layout == 0 && game_ps.buttons == kPlayStationMapping);
    constexpr auto game_custom = ResolveSessionButtonMapping(
        0, kPlayStationMapping, 0, true, kSwitchMapping);
    static_assert(game_custom.buttons == kSwitchMapping);
    // Selected prelaunch input is stable throughout menus/gameplay:
    constexpr auto same = ResolveSessionButtonMapping(
        0, kPlayStationMapping, 1, false, kPlayStationMapping);
    static_assert(same.buttons == game_layout.buttons);
    constexpr auto global_custom = ResolveSessionButtonMapping(
        0, kSwitchMapping, -1, false, kPlayStationMapping);
    static_assert(global_custom.buttons == kSwitchMapping);
    assert(game_layout.buttons[game_a] == pad_circle);
    assert(game_ps.buttons[game_a] == pad_cross);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-ps5-fixed-input-") as work:
    cpp = Path(work) / "mapping.cpp"
    exe = Path(work) / "mapping"
    cpp.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "headless"), str(cpp), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: fixed global and per-game PS5 mapping before boot; no runtime swapping")
print("NOTE: Nintendo in-game glyph artwork remains a separate RomFS requirement")
