#!/usr/bin/env python3
"""Compile FC27 PS5 Auto input context regression with real C++ policy.

Nintendo HID exposes no generic "FC27 menu/scene" flag. Only a qualified
quiet+navigation sequence may restore menu semantics; Touchpad+Square allows
explicit override. Switch/custom mappings never enter this automatic mode.
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
assert "mapping_context.manual_toggle()" in pad
assert "kButtonTouchPad | kButtonSquare" in pad
assert 'reason=manual_chord' in pad
assert 'reason=%s sticky=0' in pad
assert "kAutoControls.quiet_polls_before_dpad * 8u" in pad
assert "kAutoControls.menu_evidence_enter" in pad
assert "const bool navigation_edge = " in pad
assert "sample.buttons &= ~(kButtonTouchPad | kButtonSquare);" in pad
assert "slot.touch_chord = true;" in pad
assert "pad->SetAdaptivePlayStation(effective_layout == 0 && !custom_mapping);" in launcher
assert "pad->SetAdaptivePlayStation(false);" not in launcher

compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if compiler is None:
    raise SystemExit("C++20 compiler required")
code = r"""
#include "playstation_auto_context.h"
#include "button_mapping.h"
#include <cassert>
using namespace Eden;
using Context = Controls::PlayStationAutoContext;
using Transition = Context::Transition;
constexpr unsigned gain = 2, enter_match = 18, quiet = 600, enter_menu = 10;
constexpr unsigned nav_gain = 2, options_gain = 4;
constexpr Transition observe(Context& ctx, bool motion, bool face = false,
                             bool nav_edge = false, bool options_edge = false) {
    return ctx.observe(motion, face, nav_edge, options_edge, gain,
                       enter_match, quiet, enter_menu, nav_gain, options_gain);
}
int main() {
    Context ctx;
    assert(ctx.mode() == Context::Mode::menu);
    for (unsigned i=0; i<2000; ++i) {
        assert(observe(ctx, false, false, (i%10)==0) == Transition::none);
        assert(!ctx.gameplay()); // Menu navigation never causes match mapping.
    }
    for (unsigned i=0; i<25; ++i)
        assert(observe(ctx, true, true) == Transition::none);
    assert(!ctx.gameplay()); // Do not swap while Cross/Circle is pressed.
    assert(observe(ctx, true) == Transition::to_gameplay);
    assert(ctx.gameplay());
    assert((ctx.gameplay() ? kSwitchMapping : kPlayStationMapping)[game_a] == pad_circle);

    // In-match D-pad/Options tactical commands, including long held keys,
    // cannot flip without 600 consecutive quiet samples and many edges.
    for (unsigned i=0; i<20000; ++i) {
        assert(observe(ctx, i%30 == 0, false, i%23 == 0, i%120 == 0) ==
               Transition::none);
        assert(ctx.gameplay());
    }
    for (unsigned i=0; i<quiet-1; ++i)
        assert(observe(ctx, false, false, i%15 == 0) == Transition::none);
    assert(ctx.gameplay());
    // After uninterrupted quiet, a single menu-direction tap is not
    // convincing; five separate D-pad edges qualify returning to menus.
    assert(observe(ctx, false, false, true) == Transition::none);
    for (int n=0; n<3; ++n)
        assert(observe(ctx, false, false, true) == Transition::none);
    assert(ctx.gameplay());
    assert(observe(ctx, false, false, true, false) == Transition::to_menu);
    assert(!ctx.gameplay());
    assert((ctx.gameplay() ? kSwitchMapping : kPlayStationMapping)[game_a] == pad_cross);

    for (unsigned i=0; i<9; ++i) {
        auto transition = observe(ctx, true);
        if (i<8) assert(transition == Transition::none);
        else assert(transition == Transition::to_gameplay);
    }
    // User can restore menu mapping in a screen the controller heuristics
    // cannot classify; it stays there despite subsequent joystick activity.
    assert(ctx.manual_toggle() == Transition::to_menu);
    assert(ctx.manually_selected() && !ctx.gameplay());
    for (int i=0; i<3000; ++i) {
        assert(observe(ctx, true, false, true, true) == Transition::none);
        assert(!ctx.gameplay());
    }
    // User can return to the working in-match physical mapping on demand.
    assert(ctx.manual_toggle() == Transition::to_gameplay);
    assert(ctx.gameplay());
    for (int i=0; i<3000; ++i)
        assert(observe(ctx, false, false, true, true) == Transition::none);
    assert(ctx.gameplay());
    ctx.reset();
    assert(!ctx.gameplay() && !ctx.manually_selected());
    assert(BaseMappingForLayout(1) == kSwitchMapping);
    auto custom = Assign(kPlayStationMapping, game_a, pad_triangle);
    assert(MappingIsCustom(custom, 0));
}
"""
with tempfile.TemporaryDirectory(prefix="eden-ps5-auto-context-") as work:
    cpp = Path(work) / "check.cpp"
    exe = Path(work) / "check"
    cpp.write_text(code)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "headless"), str(cpp), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: PS5 Auto menu reentry after quiet navigation, live match layout preserved, manual override stable")
print("NOTE: no generic title scene signal; in-game PlayStation glyph art requires title assets")
