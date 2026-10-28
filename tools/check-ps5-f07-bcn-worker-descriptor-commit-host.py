#!/usr/bin/env python3
"""BCn3D VkDescriptorSet commit must execute on FIFO worker, not texture lock."""
from pathlib import Path
import shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"vendor/encore-active/eden-vulkan/vk_compute_pass_cost.cpp").read_text()
pinned=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_compute_pass.cpp").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
start=source.index("void BlockLinearUnswizzle3DPass::UnswizzleChunk(")
end=source.index("\n} // namespace Vulkan",start)
method=source[start:end]
owner="#ifndef PS5_NATIVE\n    const VkDescriptorSet set = descriptor_allocator.Commit();\n#endif"
worker="#ifdef PS5_NATIVE\n        // Mirror the other compute passes: allocate the Vulkan descriptor set\n        // on the FIFO worker, outside the caller's texture-cache lock.\n        const VkDescriptorSet set = descriptor_allocator.Commit();\n#endif"
assert method.count(owner)==1
assert method.count(worker)==1
assert method.count("descriptor_allocator.Commit();")==2
assert method.index(owner) < method.index("    scheduler.Record(") < method.index(worker)
assert method.index(worker) < method.index("device.GetLogical().UpdateDescriptorSet")
assert method.index("if (dst_image == VK_NULL_HANDLE || out_buffer == VK_NULL_HANDLE)") < method.index(worker)
assert source.count("descriptor_allocator.Commit();")==7
assert pinned.count("const VkDescriptorSet set = descriptor_allocator.Commit();")==6
for label in ("F07 defer PS5 BCn3D descriptor set allocation from owner",
              "F07 omit BCn3D descriptor set owner capture on native worker",
              "F07 commit native BCn3D descriptor set on Vulkan worker"):
    assert label in generator,label
assert "#ifdef PS5_NATIVE\n    scheduler.Record([this, descriptor_data" in method
assert "#else\n    scheduler.Record([this, set, descriptor_data" in method
for wf in (".github/workflows/encore-core-fast-gate.yml",
           ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-bcn-worker-descriptor-commit-host.py" in (ROOT/wf).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <utility>
using VkDescriptorSet=std::uint64_t;
struct Allocator {
    unsigned calls{};
    unsigned owner_calls{};
    bool owner_locked{};
    VkDescriptorSet Commit() {
        ++calls;
        if (owner_locked) ++owner_calls;
        return calls;
    }
};
struct Device {
    unsigned updates{};
    unsigned last_set{};
    Device& GetLogical() { return *this; }
    void UpdateDescriptorSet(VkDescriptorSet set,int,const void*) {
        assert(set!=0);
        last_set=static_cast<unsigned>(set);
        ++updates;
    }
};
struct Pass {
    Allocator descriptor_allocator{};
    Device device{};
    int templ=3;
    int* descriptor_template=&templ;
    int payload=91;
    std::function<void()> queued{};
    void Enqueue(bool valid,bool reject=false) {
        descriptor_allocator.owner_locked=true;
        const void* descriptor_data=&payload;
""" + owner + r"""
#ifdef PS5_NATIVE
        auto callback=[this,valid,descriptor_data]() {
#else
        auto callback=[this,set,valid,descriptor_data]() {
#endif
            if(!valid) return;
""" + worker + r"""
            device.GetLogical().UpdateDescriptorSet(set,*descriptor_template,descriptor_data);
        };
        descriptor_allocator.owner_locked=false;
        if(reject) throw std::runtime_error("simulated queue rejection");
        queued=std::move(callback);
    }
    void Execute() {
        assert(queued);
        auto work=std::move(queued);
        queued={};
        work();
    }
};
int main() {
    Pass pass;
    pass.Enqueue(true);
#ifdef PS5_NATIVE
    assert(pass.descriptor_allocator.calls==0);
#else
    assert(pass.descriptor_allocator.calls==1);
#endif
    pass.Execute();
    assert(pass.descriptor_allocator.calls==1);
    assert(pass.device.updates==1);
    pass.Enqueue(false);
#ifdef PS5_NATIVE
    assert(pass.descriptor_allocator.calls==1);
#else
    assert(pass.descriptor_allocator.calls==2);
#endif
    pass.Execute();
    assert(pass.device.updates==1);
    try { pass.Enqueue(true,true); assert(false); }
    catch(const std::runtime_error&) {}
#ifdef PS5_NATIVE
    assert(pass.descriptor_allocator.calls==1);
#else
    assert(pass.descriptor_allocator.calls==3);
#endif
    pass.Enqueue(true);
    pass.Execute();
#ifdef PS5_NATIVE
    assert(pass.descriptor_allocator.calls==2);
    assert(pass.descriptor_allocator.owner_calls==0);
#else
    assert(pass.descriptor_allocator.calls==4);
    assert(pass.descriptor_allocator.owner_calls==4);
#endif
    assert(pass.device.updates==2);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-bcn-worker-set-") as temp:
    unit=Path(temp)/"test.cpp"
    unit.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            out=Path(temp)/(("native" if native else "desktop")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",*flags,str(unit),"-o",str(out)],
                 capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-4000:])
print("F07_BCN3D_DESCRIPTOR_WORKER_PASS source_extracted=1 owner_allocations_native=0 desktop_original=1 rejected_no_alloc=1 zero_handle_no_alloc=1 O0=1 O2=1 UBSan=1")
