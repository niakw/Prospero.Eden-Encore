#!/usr/bin/env python3
"""Source-extracted native zero-descriptor queue path, no fake GPU waits."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
header=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h").read_text()
gfx=(root/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
fn="    void AcquireKnownEmpty(bool use_descriptor_buffer_) noexcept {"
assert header.count(fn)==1
empty=header[header.index(fn):header.index("    template <typename WaitWorker>",header.index(fn))]
assert empty.count("upload_start = payload_cursor;")==1
assert "scheduler" not in empty and "WaitWorker" not in empty
begin=gfx.index("if (num_descriptor_entries == 0) {")
end=gfx.index("\n    }",begin)
branch=gfx[begin:end]
assert branch.count("AcquireKnownEmpty(uses_descriptor_buffer)") == 1
assert branch.count("guest_descriptor_queue.Acquire(scheduler, num_descriptor_entries, uses_descriptor_buffer)") == 1
constructor=gfx[gfx.index("GraphicsPipeline::GraphicsPipeline("):gfx.index("fragment_has_color0_output",gfx.index("GraphicsPipeline::GraphicsPipeline("))]
assert "num_descriptor_entries += NumDescriptorEntries(*info);" in constructor
oracle=(root/"tools/prepare-vulkan-port.py").read_text()
assert "phase == 'DescriptorQueueAcquire'" in oracle
assert "void AcquireKnownEmpty(bool use_descriptor_buffer_) noexcept" in oracle
# Existing release queue default must stay 1024 for callers passing zero.
pinned=(root/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_update_descriptor.cpp").read_text()
assert "const size_t reserve = required_entries > 0 ? required_entries : DEFAULT_REQUIRED_ENTRIES;" in pinned
stub=r'''
#include <cassert>
#include <cstddef>
struct Scheduler { unsigned waits=0; void WaitWorker(){++waits;} };
struct UpdateDescriptorQueue {
    int payload[2048]{};
    int* payload_start=payload;
    int* payload_cursor=payload;
    int* upload_start=nullptr;
    bool supports_descriptor_buffer=true;
    bool use_descriptor_buffer=false;
    void Acquire(Scheduler& scheduler, std::size_t entries, bool use) {
        use_descriptor_buffer=supports_descriptor_buffer&&use;
        const std::size_t required=entries>0?entries:1024;
        if (static_cast<std::size_t>(payload_cursor-payload_start)+required>=2048) {
            scheduler.WaitWorker();
            payload_cursor=payload_start;
        }
        upload_start=payload_cursor;
    }
''' + empty + r'''
};
struct GraphicsPipeline {
    std::size_t num_descriptor_entries{};
    bool uses_descriptor_buffer{};
    Scheduler scheduler;
    UpdateDescriptorQueue guest_descriptor_queue;
    void Configure(){
''' + branch + r'''
    }
};
int main() {
    GraphicsPipeline p;
    p.guest_descriptor_queue.payload_cursor += 1800;
    p.uses_descriptor_buffer=true;
    p.Configure();
    assert(p.scheduler.waits==0);
    assert(p.guest_descriptor_queue.upload_start==p.guest_descriptor_queue.payload+1800);
    assert(p.guest_descriptor_queue.use_descriptor_buffer);
    p.num_descriptor_entries=500;
    p.Configure();
    assert(p.scheduler.waits==1);
    assert(p.guest_descriptor_queue.upload_start==p.guest_descriptor_queue.payload);
    p.guest_descriptor_queue.supports_descriptor_buffer=false;
    p.num_descriptor_entries=0;
    p.Configure();
    assert(!p.guest_descriptor_queue.use_descriptor_buffer);
    assert(p.scheduler.waits==1);
}
'''
with tempfile.TemporaryDirectory(prefix="encore-exact-zero-desc-") as tmp:
    cpp=Path(tmp)/"test.cpp"
    cpp.write_text(stub)
    for profile in ("-O0","-O2"):
        exe=Path(tmp)/profile
        subprocess.run(["c++","-std=c++20",profile,"-Wall","-Wextra","-Werror",
                        str(cpp),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        print("ENCORE_KNOWN_EMPTY_DESCRIPTOR_SKIP_PASS",profile)
