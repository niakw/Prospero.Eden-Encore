#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F06: source-extracted EmulatedController -> NPad state handoff, O0/O2.

Runs the actual active GetNpadButtons and RequestPadStateUpdate methods with
mock controller data and kernel. Does not execute InputEngine callbacks, the
guest shared-memory LIFO, HIPC, FC27 or the console.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EMULATED = (ROOT / "vendor/encore-active/eden-core/src/hid_core/frontend/emulated_controller.cpp").read_text()
NPAD = (ROOT / "vendor/encore-active/eden-core/src/hid_core/resources/npad/npad.cpp").read_text()
PAD = (ROOT / "headless/pad.cpp").read_text()
CMAKE = (ROOT / "headless/CMakeLists.txt").read_text()
assert "vendor/encore-active/eden-core/src/hid_core/frontend/emulated_controller.cpp" in CMAKE
assert "vendor/encore-active/eden-core/src/hid_core/resources/npad/npad.cpp" in CMAKE
assert 'virtual_button_params[Settings::NativeButton::Plus].Set("button", 10);' in EMULATED
assert "Button::ButtonPlus, Button::ButtonMinus" in PAD
assert "npad->fullkey_lifo.WriteNextEntry(pad_state);" in NPAD
assert "npad->system_ext_lifo.WriteNextEntry(libnx_state);" in NPAD

def extract(text: str, signature: str) -> str:
    assert text.count(signature) == 1, ("source drift", signature)
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for end in range(brace, len(text)):
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
            if depth == 0:
                return text[start:end + 1]
    raise AssertionError("unbalanced source method " + signature)

button_source = extract(EMULATED, "NpadButtonState EmulatedController::GetNpadButtons() const {")
npad_source = extract(NPAD, "void NPad::RequestPadStateUpdate(")
assert "controller.device->GetNpadButtons();" in npad_source
assert "pad_entry.npad_buttons.raw = button_state.raw & right_button_mask;" in npad_source
assert "pad_entry.npad_buttons.raw |= button_state.raw & left_button_mask;" in npad_source
assert "controller.device->StatusUpdate();" in npad_source

cpp = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <memory>
using u64=std::uint64_t;
namespace Kernel { struct KernelCore{}; }
namespace Core::HID {
enum class NpadIdType { Player1 };
enum class NpadStyleIndex { JoyconLeft,JoyconRight,JoyconDual,GameCube,Fullkey,Handheld };
enum class NpadButton: u64 {
 None=0, A=1ULL<<0, B=1ULL<<1, X=1ULL<<2, Y=1ULL<<3,
 StickR=1ULL<<4, R=1ULL<<5, ZR=1ULL<<6, Plus=1ULL<<7,
 StickRLeft=1ULL<<8, StickRUp=1ULL<<9, StickRRight=1ULL<<10, StickRDown=1ULL<<11,
 Left=1ULL<<12, Up=1ULL<<13, Right=1ULL<<14, Down=1ULL<<15,
 StickL=1ULL<<16, L=1ULL<<17, ZL=1ULL<<18, Minus=1ULL<<19,
 StickLLeft=1ULL<<20, StickLUp=1ULL<<21, StickLRight=1ULL<<22, StickLDown=1ULL<<23,
 All=~0ULL
};
constexpr NpadButton operator|(NpadButton a,NpadButton b) { return NpadButton(u64(a)|u64(b)); }
constexpr NpadButton operator&(NpadButton a,NpadButton b) { return NpadButton(u64(a)&u64(b)); }
inline NpadButton& operator|=(NpadButton& a,NpadButton b) {a=a|b;return a;}
struct Bit { bool value=false; void Assign(bool x){value=x;} operator bool()const{return value;} };
struct NpadButtonState {
 NpadButton raw{};
 Bit left_sl{},left_sr{},right_sl{},right_sr{},zr{},zl{},l{},r{};
};
struct Stick {int x{},y{};};
struct Sticks {Stick left{},right{};};
struct PadEntry {NpadButtonState npad_buttons{};Stick l_stick{},r_stick{};};
struct TriggerState {int l_analog{},r_analog{};};
struct TriggerLevels {int left{},right{};};
struct EmulatedController {
 bool connected=true;
 bool is_configuring=false;
 int updates{};
 NpadStyleIndex style=NpadStyleIndex::Fullkey;
 struct {NpadButtonState npad_button_state{};} controller;
 NpadButton mask=NpadButton::All;
 bool IsConnected()const{return connected;}
 NpadStyleIndex GetNpadStyleIndex()const{return style;}
 void StatusUpdate(){++updates;}
 NpadButton GetTurboButtonMask()const{return mask;}
 NpadButtonState GetNpadButtons()const;
 Sticks GetSticks()const{return {{10,20},{30,40}};}
 TriggerLevels GetTriggers()const{return {5,8};}
};
__BUTTON_METHOD__
}
namespace Service::HID {
struct StubCore {
 int last_active_count{};
 void SetLastActiveController(Core::HID::NpadIdType){++last_active_count;}
};
struct NPad {
 struct ControllerData {
  Core::HID::EmulatedController* device{};
  bool is_connected=true;
  Core::HID::PadEntry npad_pad_state{};
  Core::HID::TriggerState npad_trigger_state{};
 };
 struct Holder {std::recursive_mutex* shared_mutex{};} applet_resource_holder;
 std::recursive_mutex mutex;
 ControllerData controller{};
 StubCore hid_core{};
 NPad(){applet_resource_holder.shared_mutex=&mutex;}
 ControllerData& GetControllerFromNpadIdType(u64,Core::HID::NpadIdType){return controller;}
 void DisconnectNpad(Kernel::KernelCore&,u64,Core::HID::NpadIdType){controller.is_connected=false;}
 void InitNewlyAddedController(Kernel::KernelCore&,u64,Core::HID::NpadIdType){controller.is_connected=true;}
 void RequestPadStateUpdate(Kernel::KernelCore&,u64,Core::HID::NpadIdType);
};
__NPAD_METHOD__
}
int main() {
 using namespace Core::HID;
 using namespace Service::HID;
 Kernel::KernelCore kernel;
 EmulatedController physical{};
 NPad npad{};
 npad.controller.device=&physical;
 // Fullkey guest: virtual Plus + A must survive the native Npad masks.
 physical.controller.npad_button_state.raw=NpadButton::Plus | NpadButton::A;
 npad.RequestPadStateUpdate(kernel,7,NpadIdType::Player1);
 assert((npad.controller.npad_pad_state.npad_buttons.raw & NpadButton::Plus)!=NpadButton::None);
 assert((npad.controller.npad_pad_state.npad_buttons.raw & NpadButton::A)!=NpadButton::None);
 assert(npad.hid_core.last_active_count==1);
 // Release must clear the guest-visible state, not reuse the previous frame.
 physical.controller.npad_button_state.raw=NpadButton::None;
 npad.RequestPadStateUpdate(kernel,7,NpadIdType::Player1);
 assert(npad.controller.npad_pad_state.npad_buttons.raw==NpadButton::None);
 // Disabled/turbo-filtered button cannot leak back as a stale Plus.
 physical.mask=NpadButton::A;
 physical.controller.npad_button_state.raw=NpadButton::Plus | NpadButton::A;
 npad.RequestPadStateUpdate(kernel,7,NpadIdType::Player1);
 assert(npad.controller.npad_pad_state.npad_buttons.raw==NpadButton::A);
 physical.is_configuring=true;
 npad.RequestPadStateUpdate(kernel,7,NpadIdType::Player1);
 assert(npad.controller.npad_pad_state.npad_buttons.raw==NpadButton::None);
 physical.is_configuring=false;
 // Disconnect never fabricates another Npad sample.
 physical.connected=false;
 const int prior=physical.updates;
 npad.RequestPadStateUpdate(kernel,7,NpadIdType::Player1);
 assert(physical.updates==prior && !npad.controller.is_connected);
 physical.connected=true;
 physical.mask=NpadButton::All;
 physical.controller.npad_button_state.raw=NpadButton::Plus;
 npad.RequestPadStateUpdate(kernel,7,NpadIdType::Player1);
 assert(npad.controller.is_connected);
 assert(npad.controller.npad_pad_state.npad_buttons.raw==NpadButton::Plus);
 // Right-only Joy-Con does not receive the left Minus button, while Plus stays.
 physical.style=NpadStyleIndex::JoyconRight;
 physical.controller.npad_button_state.raw=NpadButton::Plus | NpadButton::Minus;
 npad.RequestPadStateUpdate(kernel,7,NpadIdType::Player1);
 assert(npad.controller.npad_pad_state.npad_buttons.raw==NpadButton::Plus);
 std::puts("F06_NATIVE_NPAD_HANDOFF_PASS plus=1 releases=1 masks=1 "
           "config_filter=1 disconnect=1 reconnect=1 joycon_right=1 "
           "scope=source_extracted_mock_controller_no_guest_lifo");
}
""".replace("__BUTTON_METHOD__", button_source).replace("__NPAD_METHOD__", npad_source)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f06-npad-handoff-") as tmp:
    src = Path(tmp) / "npad.cpp"
    src.write_text(cpp)
    for mode in ("-O0", "-O2"):
        binary = Path(tmp) / ("npad" + mode)
        build = subprocess.run(
            [compiler, "-std=c++20", mode, "-Wall", "-Wextra", "-Werror",
             "-fsanitize=undefined", "-fno-sanitize-recover=all",
             str(src), "-o", str(binary)],
            capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, (mode, build.stderr[-6000:])
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, (mode, run.stderr[-6000:], run.stdout)
        assert run.stdout.count("F06_NATIVE_NPAD_HANDOFF_PASS plus=1") == 1
        print(run.stdout.strip(), mode, flush=True)
print("F06_GUEST_LIFO_GAME_ACTIONS_AND_FC27_PHASE_PROGRESS_NOT_PROVEN")
