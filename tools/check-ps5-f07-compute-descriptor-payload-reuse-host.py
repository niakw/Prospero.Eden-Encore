#!/usr/bin/env python3
"""F07 compute descriptor reuse: native source-extracted O0/O2 regression."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
base = root / "vendor/encore-active/eden-vulkan"
src = (base/"vk_compute_pipeline_cost.cpp").read_text()
hdr = (base/"include/video_core/renderer_vulkan/vk_compute_pipeline.h").read_text()
gen = (root/"tools/prepare-vulkan-port.py").read_text()
for wf in (".github/workflows/encore-core-fast-gate.yml",
           ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-compute-descriptor-payload-reuse-host.py" in (root/wf).read_text()
needle="    const DescriptorUpdateEntry* const descriptor_data{guest_descriptor_queue.UpdateData()};"
assert src.count(needle)==1
code=src[src.index(needle):src.index("    const bool bind_descriptor_buffer{",src.index(needle))]
assert "reuse_allocation" in code and "descriptor_buffer_ring.TouchFrame(scheduler);" in code
assert "last_descriptor_buffer_valid = true;" in code
assert code.index("WriteDescriptorBuffer(")<code.index("last_descriptor_buffer_valid = true;")
assert "last_descriptor_payload.reserve(num_descriptor_entries);" in src
assert "last_descriptor_payload" in hdr and "CurrentGeneration()" in hdr
assert "F07 compute descriptor payload fast reuse" in gen
old = r'''    const DescriptorUpdateEntry* const descriptor_data{guest_descriptor_queue.UpdateData()};
    VkDeviceSize descriptor_buffer_offset{};
    u32 descriptor_buffer_chunk{};
    if (uses_descriptor_buffer) {
        const DescriptorBufferRing::Allocation alloc{
            descriptor_buffer_ring.Allocate(scheduler, descriptor_buffer_layout.size)};
        if (!alloc.host) {
            LOG_DEBUG(Render_Vulkan, "Failed to reserve descriptor memory, skipping dispatch");
            return false;
        }
        WriteDescriptorBuffer(device, descriptor_buffer_layout, descriptor_data, alloc.host);
        descriptor_buffer_offset = alloc.offset;
        descriptor_buffer_chunk = alloc.chunk;
    }
'''
cpp=r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
using u32=std::uint32_t; using u64=std::uint64_t; using VkDeviceSize=std::uint64_t;
#define LOG_DEBUG(...) ((void)0)
struct DescriptorUpdateEntry { u64 bits{}; };
struct DescriptorBufferLayout { VkDeviceSize size{16}; };
struct Device {}; struct Scheduler {};
struct GuestQueue {
    std::array<DescriptorUpdateEntry,2> entries{{{11},{22}}};
    const DescriptorUpdateEntry* UpdateData() const { return entries.data(); }
};
struct Ring {
    struct Allocation { unsigned char* host{}; VkDeviceSize offset{}; u32 chunk{}; u64 generation{}; };
    u64 generation{7}; unsigned count{},touched{}; bool reject{};
    std::array<std::array<unsigned char,16>,16> memory{};
    u64 CurrentGeneration() const {return generation;}
    Allocation Allocate(Scheduler&,VkDeviceSize size) {
        if(reject)return {};
        assert(size==16 && count<memory.size());
        const u32 index=count++;
        return {memory[index].data(),index*16u,index,generation};
    }
    void TouchFrame(Scheduler&){++touched;}
};
using DescriptorBufferRing=Ring;
void WriteDescriptorBuffer(const Device&,const DescriptorBufferLayout&,
    const DescriptorUpdateEntry* src,unsigned char* dst){std::memcpy(dst,src,16);}
struct Pipeline {
    Device device; Scheduler scheduler; GuestQueue guest_descriptor_queue;
    Ring descriptor_buffer_ring; DescriptorBufferLayout descriptor_buffer_layout;
    std::vector<DescriptorUpdateEntry> last_descriptor_payload;
    VkDeviceSize last_descriptor_buffer_offset{};
    u32 last_descriptor_buffer_chunk{}; u64 last_descriptor_buffer_generation{};
    bool last_descriptor_buffer_valid{}; u32 num_descriptor_entries{2};
    bool uses_descriptor_buffer{true};
    VkDeviceSize used_offset{}; u32 used_chunk{};
    bool Run() {
__BLOCK__
        used_offset=descriptor_buffer_offset; used_chunk=descriptor_buffer_chunk;
        return true;
    }
};
int main(){
    Pipeline p; p.last_descriptor_payload.reserve(2);
    assert(p.Run()); assert(p.descriptor_buffer_ring.count==1);
    const auto first=p.used_offset;
    (void)first; // Desktop still compiles with -Werror; only native reuses.
    assert(p.Run());
#ifdef PS5_NATIVE
    assert(p.descriptor_buffer_ring.count==1 && p.descriptor_buffer_ring.touched==1);
    assert(p.used_offset==first);
#else
    assert(p.descriptor_buffer_ring.count==2);
#endif
    p.guest_descriptor_queue.entries[1].bits=23; assert(p.Run());
#ifdef PS5_NATIVE
    assert(p.descriptor_buffer_ring.count==2);
#else
    assert(p.descriptor_buffer_ring.count==3);
#endif
    ++p.descriptor_buffer_ring.generation; assert(p.Run());
#ifdef PS5_NATIVE
    assert(p.descriptor_buffer_ring.count==3 && p.last_descriptor_buffer_generation==8);
#else
    assert(p.descriptor_buffer_ring.count==4);
#endif
    p.descriptor_buffer_ring.reject=true;
    p.guest_descriptor_queue.entries[0].bits=55;
    assert(!p.Run());
#ifdef PS5_NATIVE
    assert(p.last_descriptor_payload[0].bits==11);
#endif
    p.descriptor_buffer_ring.reject=false; assert(p.Run());
#ifdef PS5_NATIVE
    assert(p.descriptor_buffer_ring.count==4 && p.last_descriptor_payload[0].bits==55);
#else
    assert(p.descriptor_buffer_ring.count==5);
#endif
}
'''
with tempfile.TemporaryDirectory(prefix="f07-compute-reuse-") as folder:
    folder=Path(folder)
    for opt in ("-O0","-O2"):
        for name,block,native,passing in (
            ("native",code,True,True),
            ("desktop",code,False,True),
            ("prior",old,True,False),
        ):
            source=folder/"test.cpp"
            source.write_text(cpp.replace("__BLOCK__",block))
            exe=folder/(name+opt)
            cmd=["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror"]
            if native:cmd.append("-DPS5_NATIVE")
            subprocess.run(cmd+[str(source),"-o",str(exe)],check=True,timeout=45)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert (run.returncode==0)==passing,(name,opt,run.stderr)
        print("F07_COMPUTE_DESCRIPTOR_PAYLOAD_REUSE_PASS",opt)
