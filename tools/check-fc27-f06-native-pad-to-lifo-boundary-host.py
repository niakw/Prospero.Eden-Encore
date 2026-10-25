#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F06: one linked host executable, shipping PS5 pad -> guest Npad LIFO.

The source-selected native methods are compiled in TWO independent C++
translation units. A deliberately narrow fixture-only adapter forwards
virtual A/Plus edges into the mock emulated-controller state; this does NOT
claim production InputCommon wiring, guest HIPC reads, saved game actions
or real FC27 phase execution. No runtime input or game settings are changed.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PAD_FIXTURE = ROOT / "tools/check-fc27-f06-native-pad-transition-host.py"
NPAD_FIXTURE = ROOT / "tools/check-fc27-f06-native-npad-lifo-host.py"


def replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    assert count == 1, ("source fixture drift", old[:90], count)
    return source.replace(old, new, 1)


with tempfile.TemporaryDirectory(prefix="encore-f06-linked-") as tmp:
    folder = Path(tmp)
    pad_src, npad_src = folder / "pad.cpp", folder / "npad.cpp"
    for fixture, target in ((PAD_FIXTURE, pad_src), (NPAD_FIXTURE, npad_src)):
        run = subprocess.run(
            [sys.executable, "-B", str(fixture), "--emit-cpp", str(target)],
            capture_output=True, text=True, timeout=60,
        )
        assert run.returncode == 0 and target.is_file(), (
            fixture.name, run.stderr[-4000:]
        )

    pad = pad_src.read_text()
    npad = npad_src.read_text()
    for method in ("void Pad::Consume(", "void PadEngine::SetButtonState("):
        assert method in pad, ("shipping pad source missing", method)
    for method in ("EmulatedController::GetNpadButtons()",
                   "NPad::RequestPadStateUpdate(", "NPad::OnUpdate("):
        assert method in npad, ("shipping npad source missing", method)

    # The adapter is injected only into the compiled test fixture's sink.
    # It is NEVER applied to headless/pad.cpp or the emulator's shipping HID.
    pad = replace_once(
        pad, "namespace Eden {",
        'extern "C" void F06_ForwardButton(int button, bool pressed);\n'
        'extern "C" void F06_PublishAndAssert(bool a, bool plus);\n'
        "namespace Eden {",
    )
    pad = replace_once(
        pad, "if(value) ++rises[player][button];",
        "if(value) ++rises[player][button];\n"
        "        if (player == 0) F06_ForwardButton(button, value);",
    )
    pad = replace_once(
        pad, "int main() {", 'extern "C" void F06_RunPadJourney() {',
    )
    pad = replace_once(
        pad, "using V = InputCommon::VirtualGamepad::VirtualButton;",
        "using V = InputCommon::VirtualGamepad::VirtualButton;\n"
        "    static_assert(static_cast<int>(V::ButtonA) == 0);\n"
        "    static_assert(static_cast<int>(V::ButtonPlus) == 10);",
    )
    pad = replace_once(
        pad, "pad.Consume({&state,1});",
        "pad.Consume({&state,1});\n"
        "        F06_PublishAndAssert(pad.engine->Get(V::ButtonA), "
        "pad.engine->Get(V::ButtonPlus));",
    )
    # The exported source has its standalone main replaced, not duplicated.
    npad = npad[:npad.index("\nint main() {")] + r"""
static Kernel::KernelCore f06_kernel{};
static Core::Timing::CoreTiming f06_timing{};
static Core::HID::EmulatedController f06_controller{};
static Service::HID::NPad f06_npad{};
static unsigned f06_guest_samples = 0;

extern "C" void F06_ForwardButton(int button, bool pressed) {
    using Core::HID::NpadButton;
    // The synthetic InputCommon handoff is intentionally explicit and
    // asserts that the originating virtual enum values have not shifted.
    NpadButton mapped = NpadButton::None;
    if (button == 0) mapped = NpadButton::A;
    if (button == 10) mapped = NpadButton::Plus;
    if (mapped == NpadButton::None) return;
    auto& raw = f06_controller.controller.npad_button_state.raw;
    const auto bits = static_cast<u64>(raw);
    const auto target = static_cast<u64>(mapped);
    raw = static_cast<NpadButton>(pressed ? (bits | target) : (bits & ~target));
}
extern "C" void F06_PublishAndAssert(bool expect_a, bool expect_plus) {
    using Core::HID::NpadButton;
    // The exact native NPad::OnUpdate() -> RequestPadStateUpdate()
    // -> GetNpadButtons() -> guest shared LIFO is exercised here.
    f06_npad.controller_data[0][0].device = &f06_controller;
    auto& guest = f06_npad.data.shared_memory_format
                  ->npad.npad_entry[0].internal_state;
    const int before = guest.fullkey_lifo.writes;
    f06_npad.OnUpdate(f06_kernel, f06_timing);
    assert(guest.fullkey_lifo.writes == before + 1);
    assert(guest.system_ext_lifo.writes == before + 1);
    const auto pad = guest.fullkey_lifo.ReadCurrentEntry().state;
    const auto system = guest.system_ext_lifo.ReadCurrentEntry().state;
    assert(pad.sampling_number == static_cast<u64>(before + 1));
    assert(system.sampling_number == pad.sampling_number);
    assert(system.npad_buttons.raw == pad.npad_buttons.raw);
    assert(((pad.npad_buttons.raw & NpadButton::A) != NpadButton::None)
           == expect_a);
    assert(((pad.npad_buttons.raw & NpadButton::Plus) != NpadButton::None)
           == expect_plus);
    ++f06_guest_samples;
}
extern "C" void F06_RunPadJourney();
int main() {
    F06_RunPadJourney();
    assert(f06_guest_samples >= 60);
    const auto& guest = f06_npad.data.shared_memory_format
                        ->npad.npad_entry[0].internal_state;
    assert(guest.fullkey_lifo.writes == static_cast<int>(f06_guest_samples));
    assert(guest.system_ext_lifo.writes == static_cast<int>(f06_guest_samples));
    std::printf("F06_NATIVE_PAD_NPAD_LIFO_BOUNDARY_PASS phases=5 "
                "samples=%u linked=1 mapping_locked=1 plus_release=1 "
                "scope=source_extracted_host_mock_virtual_bridge_no_real_guest_hipc\n",
                f06_guest_samples);
}
"""
    pad_src.write_text(pad)
    npad_src.write_text(npad)
    compiler = (shutil.which("clang++-18") or shutil.which("clang++")
                or shutil.which("g++"))
    assert compiler, "A C++20 compiler is required"
    for mode in ("-O0", "-O2"):
        exe = folder / ("f06" + mode)
        build = subprocess.run(
            [compiler, "-std=c++20", mode, "-Wall", "-Wextra", "-Werror",
             "-Wno-unused-parameter", "-fsanitize=undefined",
             "-fno-sanitize-recover=all", "-I", str(ROOT / "headless"),
             "-I", str(ROOT / "third_party"), str(pad_src), str(npad_src),
             "-o", str(exe)],
            capture_output=True, text=True, timeout=120,
        )
        assert build.returncode == 0, (mode, build.stderr[-8000:])
        run = subprocess.run(
            [str(exe)], capture_output=True, text=True, timeout=45,
        )
        assert run.returncode == 0, (mode, run.stderr[-8000:], run.stdout)
        assert run.stdout.count(
            "F06_NATIVE_PAD_NPAD_LIFO_BOUNDARY_PASS phases=5"
        ) == 1
        print(run.stdout.strip(), mode, flush=True)
print("F06_REAL_GAME_ACTION_MAPPING_HIPC_AND_FC27_PHASES_NOT_PROVEN")
