#!/usr/bin/env python3
"""F07: source-extracted BCn3D reservation must match its two Vulkan bindings."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vk_compute_pass_cost.cpp").read_text()
pinned=(root/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_compute_pass.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
begin="    compute_pass_descriptor_queue.Acquire(scheduler, 3);"
native="#ifdef PS5_NATIVE\n    // The BCn 3D pass has exactly two storage-buffer bindings."
anchor="    const void* descriptor_data = compute_pass_descriptor_queue.UpdateData();"
start=source.index(native)
end=source.index(anchor,start)
block=source[start:end]
assert block.count("compute_pass_descriptor_queue.Acquire(scheduler, 2);")==1
assert block.count("compute_pass_descriptor_queue.Acquire(scheduler, 3);")==1
assert block.count("compute_pass_descriptor_queue.AddBuffer(")==2
assert pinned.count(begin)>=2
assert "F07 reserve exact two native BCn3D compute descriptors" in generator
ctor=source[source.index("BlockLinearUnswizzle3DPass::BlockLinearUnswizzle3DPass("):start]
assert "std::array<VkDescriptorSetLayoutBinding, 2>" in ctor
assert "std::array<VkDescriptorUpdateTemplateEntry, 2>" in ctor
for workflow in (".github/workflows/encore-core-fast-gate.yml",
                 ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-bcn-descriptor-capacity-host.py" in (root/workflow).read_text()
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
using u64=std::uint64_t;
struct Scheduler { unsigned waits{}; };
struct Queue {
    struct Descriptor { u64 buffer{},offset{},size{}; };
    Descriptor payload[7]{};
    unsigned cursor{};
    unsigned starting{};
    unsigned last_reservation{};
    void Acquire(Scheduler& scheduler,unsigned entries) {
        last_reservation=entries;
        if (cursor+entries>=7) {
            ++scheduler.waits;
            cursor=0;
        }
        starting=cursor;
    }
    void AddBuffer(u64 buffer,u64 offset,u64 size) {
        assert(cursor<7);
        payload[cursor++]={buffer,offset,size};
    }
};
struct Staging { u64 buffer=91,offset=8; };
struct Swizzle { u64 buffer_offset=16; };
struct Image {
    u64 guest_size_bytes=128;
    u64 compute_unswizzle_buffer_size=512;
    u64 output=67;
    u64* compute_unswizzle_buffer=&output;
};
struct Pass {
    Scheduler scheduler;
    Queue compute_pass_descriptor_queue;
    Staging swizzled;
    Swizzle sw;
    Image image;
    void Dispatch() {
""" + block + r"""
    }
};
int main() {
    Pass pass;
    for(int i=0;i<3;++i) {
        pass.Dispatch();
        const auto& q=pass.compute_pass_descriptor_queue;
        assert(q.payload[q.starting].buffer==91);
        assert(q.payload[q.starting].offset==24);
        assert(q.payload[q.starting].size==112);
        assert(q.payload[q.starting+1].buffer==67);
        assert(q.payload[q.starting+1].size==512);
    }
#ifdef PS5_NATIVE
    assert(pass.compute_pass_descriptor_queue.last_reservation==2);
    assert(pass.scheduler.waits==0);
    assert(pass.compute_pass_descriptor_queue.cursor==6);
#else
    assert(pass.compute_pass_descriptor_queue.last_reservation==3);
    assert(pass.scheduler.waits==1);
    assert(pass.compute_pass_descriptor_queue.cursor==2);
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-bcn-desc-") as temp:
    unit=Path(temp)/"test.cpp"
    unit.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            output=Path(temp)/(("ps5" if native else "desktop")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *flags,str(unit),"-o",str(output)],
                                  capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            run=subprocess.run([str(output)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_BCN3D_DESCRIPTOR_CAPACITY_PASS bindings=2 writes=2 native_reserve=2 desktop_reserve=3 avoid_premature_worker_drain=1 O0=1 O2=1 UBSan=1")
