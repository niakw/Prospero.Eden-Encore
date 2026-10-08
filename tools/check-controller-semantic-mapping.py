#!/usr/bin/env python3
"""Host-compile the actual controller mapping contract, with no PS5 app build.

Protects emulator-input semantics independently of in-game glyph artwork.
This cannot fix a game's own Nintendo prompt textures or applet UI.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CXX = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if not CXX:
    raise SystemExit("C++20 compiler is required for button mapping regression")

code = r"""
#include "button_mapping.h"
#include <cassert>
#include <array>
#include <string_view>
using namespace Eden;

void check_bijection(const ButtonMapping& m) {
    assert(ValidMapping(m));
    for (int game = 0; game < kGameButtons; ++game)
        assert(MappedTo(m, m[game]) == game);
}

int main() {
    static_assert(kGameButtons == 12);
    static_assert(kPadButtons == 13);
    static_assert(kPlayStationMapping[game_a] == pad_cross);
    static_assert(kPlayStationMapping[game_b] == pad_circle);
    static_assert(kPlayStationMapping[game_x] == pad_square);
    static_assert(kPlayStationMapping[game_y] == pad_triangle);
    static_assert(kSwitchMapping[game_a] == pad_circle);
    static_assert(kSwitchMapping[game_b] == pad_cross);
    static_assert(kSwitchMapping[game_x] == pad_triangle);
    static_assert(kSwitchMapping[game_y] == pad_square);
    assert(BaseMappingForLayout(0) == kPlayStationMapping);
    assert(BaseMappingForLayout(1) == kSwitchMapping);
    assert(!MappingIsCustom(kPlayStationMapping, 0));
    assert(!MappingIsCustom(kSwitchMapping, 1));
    assert(MappingIsCustom(kPlayStationMapping, 1));

    for (const auto& base : {kPlayStationMapping, kSwitchMapping}) {
        check_bijection(base);
        // Every valid reassignment swaps the two guest functions, without
        // accidentally aliasing another action to the same physical key.
        for (int guest = 0; guest < kGameButtons; ++guest) {
            for (int target = 0; target < kPadButtons; ++target) {
                const auto original = base;
                auto candidate = Assign(base, guest, target);
                check_bijection(candidate);
                assert(candidate[guest] == target);
                const int original_guest = MappedTo(original, target);
                if (original_guest >= 0 && original_guest != guest)
                    assert(candidate[original_guest] == original[guest]);
                for (int other = 0; other < kGameButtons; ++other)
                    if (other != guest && other != original_guest)
                        assert(candidate[other] == original[other]);
            }
        }
    }
    const auto unchanged = kDefaultMapping;
    assert(Assign(unchanged, -1, pad_cross) == unchanged);
    assert(Assign(unchanged, kGameButtons, pad_cross) == unchanged);
    assert(Assign(unchanged, game_a, -1) == unchanged);
    assert(Assign(unchanged, game_a, kPadButtons) == unchanged);
    auto duplicate = unchanged;
    duplicate[game_b] = duplicate[game_a];
    assert(!ValidMapping(duplicate));
    auto out_of_range = unchanged;
    out_of_range[game_a] = kPadButtons;
    assert(!ValidMapping(out_of_range));

    // Input mapping changes guest *actions*, never the game's artwork.
    // The semantic test does not inspect or replace texture assets.
}
"""
with tempfile.TemporaryDirectory(prefix="eden-controller-semantics-") as folder:
    tmp = Path(folder)
    source, exe = tmp / "test.cpp", tmp / "test"
    source.write_text(code)
    subprocess.run([CXX, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "headless"), str(source), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("PASS controller PS5/Switch mapping semantics, bijection, custom swaps, invalid inputs")
print("In-game glyph replacement and FC27 scene-specific prompts: NOT TESTED")
