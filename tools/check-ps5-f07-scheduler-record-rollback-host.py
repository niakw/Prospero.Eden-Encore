#!/usr/bin/env python3
"""F07: a rejected Vulkan command record cannot preserve an unsubmitted binding memo."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
header=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_scheduler.h").read_text()
implementation=(root/"vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
begin="    template <typename T>\n        requires std::is_invocable_v<T, vk::CommandBuffer, vk::CommandBuffer>\n    void RecordWithUploadBuffer(T&& command) {"
stop="    template <typename T>\n        requires std::is_invocable_v<T, vk::CommandBuffer>\n    void Record(T&& c) {"
assert header.count(begin)==header.count(stop)==1
method=header[header.index(begin):header.index(stop)]
assert "#ifdef PS5_NATIVE" in method
assert "InvalidateState();" in method
assert method.index("} catch (...) {") > method.index("(void)chunk->Record(command)")
assert "F07 invalidate native Vulkan binding memo after rejected record" in generator
start=implementation.index("void Scheduler::InvalidateState() {")
invalidate=implementation[start:implementation.index("\n}",start)]
for required in ("state.graphics_pipeline = nullptr;",
                 "state.graphics_pipeline_optimized = false;",
                 "state.rescaling_defined = false;",
                 "state.descriptor_buffer_bound = false;"):
    assert required in invalidate
for path in (".github/workflows/encore-core-fast-gate.yml",
             ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-scheduler-record-rollback-host.py" in (root/path).read_text()

cpp=r"""
#include <cassert>
#include <new>
#include <stdexcept>
#include <type_traits>
namespace vk { struct CommandBuffer {}; }
struct MockChunk {
    bool refuse_once{};
    bool throw_record{};
    unsigned recorded{};
    template<typename T> bool Record(T&) {
        if (throw_record) throw std::bad_alloc{};
        if (refuse_once) { refuse_once=false; return false; }
        ++recorded;
        return true;
    }
};
struct Scheduler {
    MockChunk storage{};
    MockChunk* chunk=&storage;
    bool throw_dispatch{};
    bool pipeline_memo{true};
    bool rescaling_memo{true};
    bool descriptor_memo{true};
    bool renderpass_active{true};
    unsigned invalidations{};
    unsigned dispatches{};
    void DispatchWork() {
        if (throw_dispatch) throw std::bad_alloc{};
        ++dispatches;
    }
    void InvalidateState() {
        pipeline_memo=false;
        rescaling_memo=false;
        descriptor_memo=false;
        ++invalidations;
    }
""" + method + r"""
};
int main() {
    const auto cmd=[](vk::CommandBuffer, vk::CommandBuffer){};
    {
        Scheduler normal;
        normal.RecordWithUploadBuffer(cmd);
        assert(normal.storage.recorded==1 && normal.invalidations==0);
        assert(normal.pipeline_memo && normal.descriptor_memo);
    }
    {
        Scheduler rollover;
        rollover.storage.refuse_once=true;
        rollover.RecordWithUploadBuffer(cmd);
        assert(rollover.dispatches==1 && rollover.storage.recorded==1);
        assert(rollover.invalidations==0);
    }
    for (bool fail_record : {true,false}) {
        Scheduler denied;
        denied.storage.throw_record=fail_record;
        denied.storage.refuse_once=!fail_record;
        denied.throw_dispatch=!fail_record;
        bool failed=false;
        try { denied.RecordWithUploadBuffer(cmd); }
        catch(const std::bad_alloc&) { failed=true; }
        assert(failed && denied.storage.recorded==0);
#ifdef PS5_NATIVE
        assert(denied.invalidations==1);
        assert(!denied.pipeline_memo && !denied.rescaling_memo && !denied.descriptor_memo);
#else
        assert(denied.invalidations==0);
        assert(denied.pipeline_memo && denied.rescaling_memo && denied.descriptor_memo);
#endif
        assert(denied.renderpass_active);
        denied.storage.throw_record=false;
        denied.storage.refuse_once=false;
        denied.throw_dispatch=false;
        denied.RecordWithUploadBuffer(cmd);
        assert(denied.storage.recorded==1);
    }
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-record-memo-") as temp:
    unit=Path(temp)/"test.cpp"
    unit.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            output=Path(temp)/(("ps5" if native else "desktop")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            built=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *flags,str(unit),"-o",str(output)],
                                  capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-4000:])
            tested=subprocess.run([str(output)],capture_output=True,text=True,timeout=15)
            assert tested.returncode==0,(native,opt,tested.stderr[-4000:])
print("F07_SCHEDULER_RECORD_ROLLBACK_PASS first_accept=1 rollover=1 reject_record=1 reject_dispatch=1 replay=1 renderpass_preserved=1 desktop_original=1 O0=1 O2=1 UBSan=1")
