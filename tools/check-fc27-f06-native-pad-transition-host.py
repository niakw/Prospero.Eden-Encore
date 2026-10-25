#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F06: source-extracted DualSense -> virtual guest button transitions, O0/O2.

Execute shipping Pad::Consume and PadEngine::SetButtonState, not a rewritten
input map. Model title-controlled pause/half-time/end as repeated input phases;
no FC27 guest action save, HIPC consumption or console behavior is claimed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PAD = (ROOT / "headless/pad.cpp").read_text()
HEADER = (ROOT / "headless/devices.h").read_text()
CMAKE = (ROOT / "headless/CMakeLists.txt").read_text()
assert "pad.cpp" in CMAKE
assert "void Consume(std::size_t player, std::span<const ps5::pad::Data> samples);" in HEADER
assert "void SetButtonState(std::size_t player, int button, bool value);" in HEADER
assert "const auto& active_mapping = ActiveMapping();" in PAD
assert "if (pad == pad_touchpad) continue;" in PAD
assert "constexpr unsigned kSelectTapPolls = 25;" in PAD
assert "constexpr unsigned kSelectHoldPolls = 60;" in PAD

def extract(signature: str) -> str:
    assert PAD.count(signature) == 1, ("native source drift", signature)
    start = PAD.index(signature)
    opening = PAD.index("{", start)
    depth = 0
    for end in range(opening, len(PAD)):
        if PAD[end] == "{":
            depth += 1
        elif PAD[end] == "}":
            depth -= 1
            if not depth:
                return PAD[start:end + 1]
    raise AssertionError("unbalanced native method " + signature)

native_methods = "\n\n".join(extract(signature) for signature in (
    "void PadEngine::SetButtonState(std::size_t player, int button, bool value) {",
    "void PadEngine::SetButtonState(std::size_t player, VirtualButton button, bool value) {",
    "void Pad::Consume(std::size_t player, std::span<const ps5::pad::Data> samples) {",
))

cpp = r"""
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <numbers>
#include <span>
#include <utility>
#include "button_mapping.h"
#include "ps5_guest_system_button_route.h"
#include "ps5_pad.hpp"
using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
constexpr int kRightSL = 20;
constexpr int kRightSR = 21;
constexpr unsigned kSelectTapPolls = 25;
constexpr unsigned kSelectHoldPolls = 60;
namespace NativeLogs { inline bool Detailed() { return false; } }
namespace InputCommon {
struct VirtualGamepad {
    enum class VirtualButton {
        ButtonA, ButtonB, ButtonX, ButtonY, StickL, StickR, TriggerL,
        TriggerR, TriggerZL, TriggerZR, ButtonPlus, ButtonMinus, ButtonLeft,
        ButtonUp, ButtonRight, ButtonDown, ButtonSL, ButtonSR, ButtonHome,
        ButtonCapture
    };
};
}
namespace Eden {
struct EdgeDiagnostics { void Observe(...) {} };
class PadEngine {
public:
    using VirtualButton = InputCommon::VirtualGamepad::VirtualButton;
    static constexpr std::size_t kPlayers = 10;
    static constexpr int kTrackedButtons = 22;
    std::array<std::array<u8,kTrackedButtons>,kPlayers> button_cache{};
    std::array<std::array<bool,kTrackedButtons>,kPlayers> values{};
    std::array<std::array<unsigned,kTrackedButtons>,kPlayers> writes{};
    std::array<std::array<unsigned,kTrackedButtons>,kPlayers> rises{};
    std::atomic<unsigned long long> published_plus_edges{0};
    std::atomic<unsigned long long> published_home_edges{0};
    std::atomic<unsigned long long> published_capture_edges{0};
    PadEngine() { for(auto& b:button_cache) b.fill(2); }
    std::size_t Identifier(std::size_t player) const { return player; }
    void SetButton(std::size_t player,int button,bool value) {
        assert(player < kPlayers && button >= 0 && button < kTrackedButtons);
        values[player][button] = value;
        ++writes[player][button];
        if(value) ++rises[player][button];
    }
    void SetButtonState(std::size_t player,int button,bool value);
    void SetButtonState(std::size_t player,VirtualButton button,bool value);
    void SetStickPosition(std::size_t,int,float,float) {}
    void SetMotionAtRest(std::size_t) {}
    void SetMotionState(std::size_t,u64,float,float,float,float,float,float) {}
    bool Get(VirtualButton button) const {
        return values[0][static_cast<int>(button)];
    }
    unsigned Rising(VirtualButton button) const {
        return rises[0][static_cast<int>(button)];
    }
    unsigned Writes(VirtualButton button) const {
        return writes[0][static_cast<int>(button)];
    }
};
class Pad {
public:
    struct Slot {
        int user{-1};
        int handle{-1};
        u32 last_buttons{};
        u64 last_motion_us{};
        bool touch_chord{};
        GuestSystemButtonRoute guest_home{};
        bool select_held{};
        unsigned touch_polls{};
        unsigned select_pulse{};
    };
    std::shared_ptr<PadEngine> engine=std::make_shared<PadEngine>();
    std::array<Slot,4> slots{};
    ButtonMapping mapping=kDefaultMapping;
    float deadzone{0.08f},trigger_threshold{0.5f};
    bool return_to_menu{},hud_toggle{};
    u64 options_edges{},create_edges{};
    EdgeDiagnostics face_edges{};
    const ButtonMapping& ActiveMapping() const noexcept {return mapping;}
    void SetMapping(const ButtonMapping& value) {
        if(slots[0].handle>=0) return;
        mapping=ValidMapping(value)?value:kDefaultMapping;
    }
    void Consume(std::size_t player,std::span<const ps5::pad::Data> samples);
    void Consume(std::span<const ps5::pad::Data> samples) {Consume(0,samples);}
};
__NATIVE_METHODS__
} // namespace Eden

int main() {
    using namespace Eden;
    using namespace ps5::pad;
    using V = InputCommon::VirtualGamepad::VirtualButton;
    Pad pad;
    // A physical Circle now presses guest A; physical Cross presses guest B.
    const auto custom=Assign(kPlayStationMapping,game_a,pad_circle);
    assert(ValidMapping(custom));
    pad.SetMapping(custom);
    assert(pad.ActiveMapping()==custom);
    // Session lock cannot change gameplay mapping during the match.
    pad.slots[0].handle=3;
    pad.SetMapping(kSwitchMapping);
    assert(pad.ActiveMapping()==custom);
    u64 time=0;
    const auto step=[&](ButtonMask buttons, bool connected=true) {
        auto state=neutral_data(++time*4000);
        state.connected=connected?1:0;
        state.buttons=buttons;
        pad.Consume({&state,1});
    };
    // Five real input phases: no emulator-injected gameplay-style remap.
    for(const char* phase : {"kickoff","pause","half-time","resume","end"}) {
        (void)phase;
        step(kButtonCircle);
        assert(pad.engine->Get(V::ButtonA));
        assert(!pad.engine->Get(V::ButtonB));
        const auto before=pad.engine->Writes(V::ButtonA);
        for(int repeat=0;repeat<10;++repeat) step(kButtonCircle);
        assert(pad.engine->Writes(V::ButtonA)==before);
        step(0);
        assert(!pad.engine->Get(V::ButtonA));
        step(kButtonOptions);
        assert(pad.engine->Get(V::ButtonPlus));
        step(0);
        assert(!pad.engine->Get(V::ButtonPlus));
    }
    assert(pad.engine->Rising(V::ButtonA)==5);
    assert(pad.engine->Rising(V::ButtonPlus)==5);
    // Held action vanishes on intercepted/disconnected physical sampling.
    step(kButtonCircle);
    assert(pad.engine->Get(V::ButtonA));
    step(kButtonCircle,false);
    assert(!pad.engine->Get(V::ButtonA));
    // Touchpad+Options maps to guest Home and never leaks guest Plus/Minus.
    step(kButtonTouchPad|kButtonOptions);
    assert(pad.engine->Get(V::ButtonHome));
    assert(!pad.engine->Get(V::ButtonPlus));
    assert(!pad.engine->Get(V::ButtonMinus));
    step(kButtonOptions);
    assert(!pad.engine->Get(V::ButtonHome));
    assert(!pad.engine->Get(V::ButtonPlus));
    step(0);
    // Local menu shortcut must not produce gameplay shoulder/Minus keys.
    step(kButtonTouchPad|kButtonL1);
    assert(pad.return_to_menu);
    assert(!pad.engine->Get(V::TriggerL));
    assert(!pad.engine->Get(V::ButtonMinus));
    step(0);
    // A standalone touchpad tap is Minus, then auto-releases.
    step(kButtonTouchPad);
    step(0);
    assert(pad.engine->Get(V::ButtonMinus));
    for(int i=0;i<28;++i)pad.Consume(std::span<const Data>{});
    assert(!pad.engine->Get(V::ButtonMinus));
    assert(pad.engine->Rising(V::ButtonMinus)==1);
    assert(pad.engine->Rising(V::ButtonPlus)==5);
    std::puts("F06_NATIVE_PAD_TRANSITIONS_PASS phases=5 action_edges=5 "
              "options_plus_edges=5 disconnect_releases=1 "
              "home_chords=1 menu_shortcuts=1 touch_taps=1 "
              "scope=source_extracted_host_mock_virtual_input_no_guest_Npad");
}
""".replace("__NATIVE_METHODS__",native_methods)

# Export the exact generated, source-extracted fixture for the linked F06
# boundary regression. Default standalone execution remains unchanged.
import sys
if len(sys.argv) == 3 and sys.argv[1] == "--emit-cpp":
    Path(sys.argv[2]).write_text(cpp)
    raise SystemExit(0)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 host compiler needed"
with tempfile.TemporaryDirectory(prefix="encore-f06-native-pad-") as temp:
    root=Path(temp)
    source=root/"pad.cpp"
    source.write_text(cpp)
    for opt in ("-O0","-O2"):
        target=root/("pad"+opt)
        build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra",
            "-Werror","-Wno-unused-parameter","-fsanitize=undefined","-fno-sanitize-recover=all",
            "-I",str(ROOT/"headless"),"-I",str(ROOT/"third_party"),
            str(source),"-o",str(target)],capture_output=True,text=True,timeout=90)
        assert build.returncode==0,(opt,build.stderr[-6000:])
        run=subprocess.run([str(target)],capture_output=True,text=True,timeout=30)
        assert run.returncode==0,(opt,run.stderr[-6000:],run.stdout)
        assert run.stdout.count("F06_NATIVE_PAD_TRANSITIONS_PASS phases=5")==1
        print(run.stdout.strip(),opt,flush=True)
print("F06_REAL_GUEST_NPAD_GAMEPLAY_MAPPING_AND_MATCH_PROGRESS_NOT_PROVEN")
