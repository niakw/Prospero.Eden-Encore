#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F06: execute native EmulatedController -> NPad -> guest LIFO publication.

Extracts three *shipping* methods and compiles them together at O0/O2 with
mock controller/kernel/shared-memory storage. Does not execute PS5 scePad,
the guest HIPC consumer, FC27's own configuration or a match transition.
"""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
base_file = ROOT / "tools/check-fc27-f06-native-npad-handoff-host.py"
base_source = base_file.read_text()
NPAD = (ROOT / "vendor/encore-active/eden-core/src/hid_core/resources/npad/npad.cpp").read_text()
EMULATED = (ROOT / "vendor/encore-active/eden-core/src/hid_core/frontend/emulated_controller.cpp").read_text()
CMAKE = (ROOT / "headless/CMakeLists.txt").read_text()
assert "vendor/encore-active/eden-core/src/hid_core/resources/npad/npad.cpp" in CMAKE
assert "vendor/encore-active/eden-core/src/hid_core/frontend/emulated_controller.cpp" in CMAKE
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
    raise AssertionError("unbalanced native function: " + signature)

# Share the already maintained F06 native-input witness' mock types, but
# extract the actual methods anew. AST reads only a literal template: no eval,
# imports or execution of another test as a side-effect.
tree = ast.parse(base_source)
templates = [
    node.value for node in ast.walk(tree)
    if isinstance(node, ast.Constant) and isinstance(node.value, str)
    and "__BUTTON_METHOD__" in node.value and "__NPAD_METHOD__" in node.value
    and "namespace Service::HID" in node.value
]
assert len(templates) == 1, "base native-input mock template drift"
cpp = templates[0]

def once(old: str, new: str) -> None:
    global cpp
    assert cpp.count(old) == 1, ("fixture source drift", old[:90], cpp.count(old))
    cpp = cpp.replace(old, new, 1)

once('#include <memory>', '#include <memory>\n#include <utility>')
once('namespace Kernel { struct KernelCore{}; }',
     'namespace Kernel { struct KernelCore{}; }\n'
     'namespace Core::Timing {struct CoreTiming{};}\n'
     '#define LOG_WARNING(...) ((void)0)\n'
     'template<typename... T> void Sink(const T&...) {}\n'
     '#define LOG_INFO(cat, fmt, ...) Sink(__VA_ARGS__)\n'
     '#define ASSERT(x) assert(x)')
once('enum class NpadStyleIndex { JoyconLeft,JoyconRight,JoyconDual,GameCube,Fullkey,Handheld };',
     'enum class NpadStyleIndex { None,JoyconLeft,JoyconRight,JoyconDual,GameCube,'
     'Fullkey,Handheld,NES,SNES,N64,SegaGenesis,Pokeball };')
once('struct PadEntry {NpadButtonState npad_buttons{};Stick l_stick{},r_stick{};};',
     'struct ConnectionStatus {int raw{}; Bit is_connected{},is_wired{},is_left_connected{},'
     'is_right_connected{},is_left_wired{},is_right_wired{};};\n'
     'struct PadEntry {NpadButtonState npad_buttons{};Stick l_stick{},r_stick{};'
     'ConnectionStatus connection_status{};u64 sampling_number{};};\n'
     'struct LibnxEntry {NpadButtonState npad_buttons{};Stick l_stick{},r_stick{};'
     'ConnectionStatus connection_status{};u64 sampling_number{};};')
once('struct TriggerState {int l_analog{},r_analog{};};',
     'struct TriggerState {int l_analog{},r_analog{};u64 sampling_number{};};')
once('NpadStyleIndex GetNpadStyleIndex()const{return style;}',
     'NpadStyleIndex GetNpadStyleIndex()const{return style;}\n'
     ' NpadIdType GetNpadIdType()const{return NpadIdType::Player1;}')

mock = r"""
namespace Service::HID {
struct StubCore {
 int last_active_count{};
 void SetLastActiveController(Core::HID::NpadIdType){++last_active_count;}
};
template<class T> struct Lifo {
 struct Entry {T state{};};
 Entry entry{};
 int writes{};
 const Entry& ReadCurrentEntry()const{return entry;}
 void WriteNextEntry(const T& data){entry.state=data;++writes;}
};
struct InternalState {
 Lifo<Core::HID::PadEntry> fullkey_lifo,handheld_lifo,joy_dual_lifo,
 joy_left_lifo,joy_right_lifo,palma_lifo;
 Lifo<Core::HID::LibnxEntry> system_ext_lifo;
 Lifo<Core::HID::TriggerState> gc_trigger_lifo;
};
struct SharedMemoryFormat {
 struct {struct {InternalState internal_state;} npad_entry[1];} npad;
};
struct AruidData {
 u64 aruid=7;
 struct {bool is_assigned=true;bool enable_pad_input=true;} flag;
 std::shared_ptr<SharedMemoryFormat> shared_memory_format=
     std::make_shared<SharedMemoryFormat>();
};
struct AppletResource {
 AruidData* data{};
 const AruidData* GetAruidDataByIndex(std::size_t i)const{return i==0?data:nullptr;}
};
struct NpadResource {
 bool enabled=true;
 void IsSupportedNpadStyleSet(bool& out,u64){out=enabled;}
};
struct NPad {
 static constexpr std::size_t AruidIndexMax=1;
 struct ControllerData {
  Core::HID::EmulatedController* device{};
  bool is_connected=true,is_active=true,is_dual_left_connected=true,
       is_dual_right_connected=true;
  InternalState* shared_memory{};
  Core::HID::PadEntry npad_pad_state{};
  Core::HID::LibnxEntry npad_libnx_state{};
  Core::HID::TriggerState npad_trigger_state{};
 };
 struct Holder {
  std::recursive_mutex* shared_mutex{};
  AppletResource* applet_resource{};
 } applet_resource_holder;
 std::recursive_mutex mutex;
 AruidData data{};
 AppletResource resource{&data};
 std::array<std::array<ControllerData,1>,AruidIndexMax> controller_data{};
 NpadResource npad_resource{};
 StubCore hid_core{};
 int ref_counter=1;
 u64 press_state{};
 NPad(){
  applet_resource_holder.shared_mutex=&mutex;
  applet_resource_holder.applet_resource=&resource;
 }
 ControllerData& GetControllerFromNpadIdType(u64,Core::HID::NpadIdType){
  return controller_data[0][0];
 }
 void DisconnectNpad(Kernel::KernelCore&,u64,Core::HID::NpadIdType){
  controller_data[0][0].is_connected=false;
 }
 void InitNewlyAddedController(Kernel::KernelCore&,u64,Core::HID::NpadIdType){
  controller_data[0][0].is_connected=true;
 }
 void RequestPadStateUpdate(Kernel::KernelCore&,u64,Core::HID::NpadIdType);
 void OnUpdate(Kernel::KernelCore&,const Core::Timing::CoreTiming&);
};
__NPAD_METHOD__
__NPAD_UPDATE__
}
"""
start = cpp.index("namespace Service::HID {")
finish = cpp.index("\nint main() {", start)
assert cpp.count("namespace Service::HID {") == 1
assert "__NPAD_METHOD__" in cpp[start:finish]
cpp = cpp[:start] + mock + cpp[finish:]
cpp = cpp[:cpp.index("\nint main() {")] + r"""
int main() {
 using namespace Core::HID;
 using namespace Service::HID;
 Kernel::KernelCore kernel;
 Core::Timing::CoreTiming timing;
 EmulatedController physical{};
 NPad npad{};
 npad.controller_data[0][0].device=&physical;
 auto& guest=npad.data.shared_memory_format->npad.npad_entry[0].internal_state;
 auto sample=[&](NpadButton buttons){
  physical.controller.npad_button_state.raw=buttons;
  npad.OnUpdate(kernel,timing);
 };
 sample(NpadButton::Plus | NpadButton::A);
 assert(guest.fullkey_lifo.writes==1 && guest.system_ext_lifo.writes==1);
 assert(guest.fullkey_lifo.ReadCurrentEntry().state.sampling_number==1);
 assert(guest.fullkey_lifo.ReadCurrentEntry().state.npad_buttons.raw==
        (NpadButton::Plus | NpadButton::A));
 assert(guest.system_ext_lifo.ReadCurrentEntry().state.npad_buttons.raw==
        (NpadButton::Plus | NpadButton::A));
 sample(NpadButton::None);
 assert(guest.fullkey_lifo.writes==2);
 assert(guest.fullkey_lifo.ReadCurrentEntry().state.npad_buttons.raw==NpadButton::None);
 assert(guest.fullkey_lifo.ReadCurrentEntry().state.sampling_number==2);
 npad.data.flag.enable_pad_input=false;sample(NpadButton::Plus);
 assert(guest.fullkey_lifo.writes==2);
 npad.data.flag.enable_pad_input=true;
 npad.npad_resource.enabled=false;sample(NpadButton::Plus);
 assert(guest.fullkey_lifo.writes==2);
 npad.npad_resource.enabled=true;
 npad.controller_data[0][0].is_active=false;sample(NpadButton::Plus);
 assert(guest.fullkey_lifo.writes==2);
 npad.controller_data[0][0].is_active=true;sample(NpadButton::Plus);
 assert(guest.fullkey_lifo.writes==3 && guest.system_ext_lifo.writes==3);
 assert(guest.fullkey_lifo.ReadCurrentEntry().state.npad_buttons.raw==NpadButton::Plus);
 assert(guest.fullkey_lifo.ReadCurrentEntry().state.sampling_number==3);
 physical.style=NpadStyleIndex::JoyconRight;
 sample(NpadButton::Plus | NpadButton::Minus);
 assert(guest.joy_right_lifo.writes==1);
 assert(guest.joy_right_lifo.ReadCurrentEntry().state.npad_buttons.raw==NpadButton::Plus);
 assert(guest.system_ext_lifo.ReadCurrentEntry().state.npad_buttons.raw==NpadButton::Plus);
 physical.style=NpadStyleIndex::Fullkey;
 physical.connected=false;sample(NpadButton::Plus);
 assert(guest.fullkey_lifo.writes==3);
 physical.connected=true;sample(NpadButton::Plus);
 assert(guest.fullkey_lifo.writes==4);
 assert(guest.fullkey_lifo.ReadCurrentEntry().state.sampling_number==4);
 npad.ref_counter=0;sample(NpadButton::None);
 assert(guest.fullkey_lifo.writes==4);
 std::puts("F06_NATIVE_NPAD_LIFO_HOST_PASS writes=4 fullkey_order=1 "
           "system_ext=1 plus_release=1 gated=1 reconnect=1 joycon_style=1 "
           "scope=source_extracted_guest_lifo_mock_shared_memory");
}
"""
button_source = extract(EMULATED, "NpadButtonState EmulatedController::GetNpadButtons() const {")
request_source = extract(NPAD, "void NPad::RequestPadStateUpdate(")
publish_source = extract(NPAD, "void NPad::OnUpdate(")
assert "npad->fullkey_lifo.WriteNextEntry(pad_state);" in publish_source
assert "npad->system_ext_lifo.WriteNextEntry(libnx_state);" in publish_source
assert "if (!data->flag.enable_pad_input)" in publish_source
for token, value in (
    ("__BUTTON_METHOD__", button_source),
    ("__NPAD_METHOD__", request_source),
    ("__NPAD_UPDATE__", publish_source),
):
    once(token, value)

# Export the exact generated, source-extracted fixture for the linked F06
# boundary regression. Default standalone execution remains unchanged.
import sys
if len(sys.argv) == 3 and sys.argv[1] == "--emit-cpp":
    Path(sys.argv[2]).write_text(cpp)
    raise SystemExit(0)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f06-npad-lifo-") as folder:
    src = Path(folder) / "npad.cpp"
    src.write_text(cpp)
    for mode in ("-O0", "-O2"):
        exe = Path(folder) / ("npad" + mode)
        build = subprocess.run(
            [compiler, "-std=c++20", mode, "-Wall", "-Wextra", "-Werror",
             "-Wno-unused-parameter", "-fsanitize=undefined",
             "-fno-sanitize-recover=all", str(src), "-o", str(exe)],
            capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, (mode, build.stderr[-6000:])
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, (mode, run.stderr[-6000:], run.stdout)
        assert run.stdout.count("F06_NATIVE_NPAD_LIFO_HOST_PASS writes=4") == 1
        print(run.stdout.strip(), mode, flush=True)
print("F06_REAL_HIPC_AND_FC27_MATCH_TRANSITIONS_NOT_PROVEN")
