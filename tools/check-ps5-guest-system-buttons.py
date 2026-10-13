#!/usr/bin/env python3
"""R390 PS5 HOME/Capture mapping: static production checks + host C++ sanitizer.

No PS5 build: only tests the pure state machine and static source wiring.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
pad=(root/"headless/pad.cpp").read_text()
devices=(root/"headless/devices.h").read_text()
test=(root/"headless/devices_check.cpp").read_text()
am=(root/"vendor/sources/eden/src/core/hle/service/am/button_poller.cpp").read_text()
emulated=(root/"vendor/sources/eden/src/hid_core/frontend/emulated_controller.cpp").read_text()
virtual=(root/"vendor/sources/eden/src/input_common/drivers/virtual_gamepad.h").read_text()
source=(root/"headless/ps5_guest_system_button_route.h").read_text()
assert "GuestSystemButtonRoute guest_home" in devices
assert "slot.guest_home.Observe(" in pad
assert "slot.guest_home.BlockChordButtons()" in pad
assert "sample.buttons &= ~(kButtonTouchPad | kButtonOptions);" in pad
assert "slot.select_pulse = 0;" in pad
assert "slot.select_held = false;" in pad
assert "Button::ButtonHome, guest_home" in pad
assert "Button::ButtonCapture," in pad
assert "PublishedHomeEdges() const noexcept" in devices
assert "PublishedCaptureEdges() const noexcept" in devices
assert "published_home_edges.fetch_add(1, std::memory_order_relaxed)" in pad
assert "published_capture_edges.fetch_add(1, std::memory_order_relaxed)" in pad
assert "create_edges=%llu" in pad
assert "published_home_edges=%llu published_capture_edges=%llu" in pad
assert "MappedTo(active_mapping, pad_create) < 0 && (sample.buttons & kButtonCreate) != 0" in pad
assert "create_free" not in pad
assert "slot.select_held || slot.select_pulse > 0" in pad
assert "if (touch && (pressed & (kButtonL1 | kButtonR1 | kButtonOptions | (gameplay_chord_held ? kButtonSquare : 0))) != 0)" in pad
assert "kButtonOptions" in pad and "Button::ButtonPlus" in pad
assert "ButtonHome" in virtual and "ButtonCapture" in virtual
assert 'virtual_button_params[Settings::NativeButton::Home].Set("button", 18);' in emulated
assert 'virtual_button_params[Settings::NativeButton::Screenshot].Set("button", 19);' in emulated
assert 'std::atomic<bool> system_buttons_enabled{true};' in (root/"vendor/sources/eden/src/hid_core/frontend/emulated_controller.h").read_text()
assert "CHECK(pad.Engine().GetButton({}, 19))" in test
assert "CHECK(pad.Engine().GetButton({}, 18))" in test
start=am.index("void ButtonPoller::OnButtonStateChanged(WindowSystem& window_system) {")
segment=am[start:start+550]
assert "#ifdef PS5_NATIVE" in segment and "(void)window_system;" in segment
assert segment.index("return;") < segment.index("#endif")
assert segment.index("#endif") < am[start:].index("window_system.OnSystemButtonPress(")
assert "GetHomeButtons()" in am and "GetCaptureButtons()" in am
cmake=(root/"headless/CMakeLists.txt").read_text()
assert 'set_property(SOURCE "${PROJECT_SOURCE_DIR}/src/core/hle/service/am/button_poller.cpp"' in cmake
assert 'TARGET_DIRECTORY core APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1"' in cmake
test_source=r"""
#include <cassert>
#include "ps5_guest_system_button_route.h"
int main() {
    using Eden::GuestSystemButtonRoute;
    GuestSystemButtonRoute route;
    assert(!route.Observe(false,false,false) && !route.BlockChordButtons());
    // Standalone Minus or Plus must remain unaffected.
    assert(!route.Observe(true,false,false) && !route.BlockChordButtons());
    assert(!route.Observe(false,false,false) && !route.BlockChordButtons());
    assert(!route.Observe(false,true,false) && !route.BlockChordButtons());
    // The special HOME combination wins while held.
    assert(route.Observe(true,true,false) && route.BlockChordButtons());
    for(int i=0;i<400;++i)
        assert(route.Observe(true,true,false) && route.BlockChordButtons());
    // Releasing either half stops HOME but blocks leaked Plus/Minus.
    assert(!route.Observe(true,false,false) && route.BlockChordButtons());
    assert(!route.Observe(false,false,false) && !route.BlockChordButtons());
    assert(route.Observe(true,true,false) && route.BlockChordButtons());
    assert(!route.Observe(false,true,false) && route.BlockChordButtons());
    assert(!route.Observe(false,false,false) && !route.BlockChordButtons());
    // Existing menu/HUD shortcuts have precedence over HOME.
    assert(!route.Observe(true,true,true) && !route.BlockChordButtons());
    assert(!route.Observe(false,false,false) && !route.BlockChordButtons());
    assert(route.Observe(true,true,false) && route.BlockChordButtons());
    assert(!route.Observe(true,true,true) && route.BlockChordButtons());
    assert(!route.Observe(false,false,false) && !route.BlockChordButtons());
}
"""
with tempfile.TemporaryDirectory(prefix="eden-r390-system-buttons-") as td:
    source_file=Path(td)/"check.cpp"
    target=Path(td)/"check"
    source_file.write_text(test_source)
    env=os.environ.copy()
    if sys.platform=="darwin" and not env.get("SDKROOT"):
        sdk=Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
        if sdk.exists():
            env["SDKROOT"]=str(sdk)
    subprocess.run(["c++","-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-I",str(root/"headless"),
                    str(source_file),"-o",str(target)],check=True,env=env,timeout=45)
    subprocess.run([str(target)],check=True,env=env,timeout=15)
print("PASS R390: HOME chord suppression, Create→Capture source, Sony PS untouched, Switch AM actions blocked")
