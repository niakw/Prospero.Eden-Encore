#!/usr/bin/env python3
"""Regression: FC27 in-match popups must not remap Cross/Circle.

Run the REAL platform-independent auto-context C++ class under a host
compiler, and inspect only the glue that depends on PS5 SDK types.
Artwork textures are not remapped by this test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
pad = (ROOT / "headless/pad.cpp").read_text()
device = (ROOT / "headless/devices.h").read_text()
launcher = (ROOT / "headless/main.cpp").read_text()
assert "Controls::PlayStationAutoContext mapping_context;" in device
assert pad.count("mapping_context.gameplay() ? kSwitchMapping : mapping;") == 2
assert "mapping_context.observe(" in pad
assert "mapping_context = MappingContext::ui" not in pad
assert "menu_evidence" not in pad
assert "quiet_polls" not in pad
assert "pad->SetAdaptivePlayStation(effective_layout == 0 && !custom_mapping);" in launcher
assert "pad->SetAdaptivePlayStation(false);" not in launcher

compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if compiler is None:
    raise SystemExit("C++20 compiler required")
fixture = r"""
#include "playstation_auto_context.h"
#include "button_mapping.h"
#include <cassert>
using namespace Eden;

int main() {
    Controls::PlayStationAutoContext ctx;
    assert(ctx.mode() == Controls::PlayStationAutoContext::Mode::menu);
    assert(!ctx.gameplay());
    // Normal title-menu navigation, including Options and D-pad, has no
    // game-motion evidence and cannot change the default PS mapping.
    for (int i = 0; i < 2500; ++i) {
        assert(!ctx.observe(false, false, 2, 18));
        assert(!ctx.gameplay());
    }
    // Simultaneous face hold must not flip A/B mapping mid-press.
    for (int i = 0; i < 50; ++i)
        assert(!ctx.observe(true, true, 2, 18));
    assert(!ctx.gameplay());
    // Once a face button is released, game motion can enter gameplay.
    assert(ctx.observe(true, false, 2, 18));
    assert(ctx.gameplay());
    const ButtonMapping& match = ctx.gameplay() ? kSwitchMapping : kPlayStationMapping;
    assert(match[game_a] == pad_circle);
    assert(match[game_b] == pad_cross);
    // A long popup/half-time menu (40 seconds of 4 ms polls) can contain
    // no motion, D-pad navigation and Options: NONE represents a real
    // title-scene signal; maintaining match face semantics avoids regressions.
    for (int i = 0; i < 10000; ++i) {
        assert(!ctx.observe(false, false, 2, 18));
        assert(ctx.gameplay());
        assert((ctx.gameplay() ? kSwitchMapping : kPlayStationMapping) == match);
    }
    // Gameplay restarts after overlay; still the same physical mapping.
    for (int i = 0; i < 1000; ++i) {
        assert(!ctx.observe(true, false, 2, 18));
        assert(ctx.gameplay());
    }
    // A different launched game creates a new Pad, and an explicit
    // reset also recovers initial title-menu semantics.
    ctx.reset();
    assert(!ctx.gameplay());
    assert(ctx.mode() == Controls::PlayStationAutoContext::Mode::menu);
    // Nintendo layout and explicit custom maps never use this policy.
    assert(BaseMappingForLayout(1) == kSwitchMapping);
    auto custom = Assign(kPlayStationMapping, game_a, pad_triangle);
    assert(MappingIsCustom(custom, 0));
}
"""
with tempfile.TemporaryDirectory(prefix="eden-ps5-auto-context-") as work:
    cpp = Path(work) / "check.cpp"
    exe = Path(work) / "check"
    cpp.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "headless"), str(cpp), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("PASS real C++ PlayStation Auto mode: modal/Options/D-pad never swap face buttons after gameplay entry")
print("NOTE controller input only; FC27 native button glyph artwork not available")
