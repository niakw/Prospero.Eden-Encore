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

# Regression for zero-descriptor payload comparison and cache snapshots.
# Keep both branches sourced from the actual selected graphics pipeline code.
import re
reuse_start=gfx.index("        const bool reuse_allocation =",
                      gfx.index("bool GraphicsPipeline::ConfigureDraw("))
reuse_end=gfx.index(";\n",reuse_start)+1
reuse_stmt=gfx[reuse_start:reuse_end]
update_start=gfx.index("        update_descriptors =",reuse_end)
update_end=gfx.index(";\n",update_start)+1
update_stmt=gfx[update_start:update_end]
buffer_start=gfx.index("            // Empty shader layouts have no descriptor payload to copy.",reuse_end)
buffer_end=gfx.index("\n        }",buffer_start)
buffer_snapshot=gfx[buffer_start:buffer_end]
set_start=gfx.index("        if (update_descriptors) {",update_start)
set_end=gfx.index("\n    }\n    scheduler.Record(",set_start)
set_snapshot=gfx[set_start:set_end]
# This fixture embeds only the legacy desktop branch inside a small C++ mock.
# The real PS5 memo lives after scheduler.Record. Do not extract the closing
# #endif without its opening #ifndef into the standalone SaveSet method.
assert set_snapshot.endswith("\n#endif")
set_snapshot=set_snapshot.removesuffix("\n#endif")
assert "(num_descriptor_entries == 0 ||" in reuse_stmt
assert "(num_descriptor_entries != 0 &&" in update_stmt
assert buffer_snapshot.count("last_descriptor_payload.clear();")==1
assert set_snapshot.count("last_descriptor_payload.clear();")==1
# Descriptor-buffer, desktop legacy and PS5 post-Record snapshots must
# each preserve the empty-vector guard.
assert gfx.count("last_descriptor_payload.assign(entries, entries + num_descriptor_entries);")==3
assert "#ifndef PS5_NATIVE" in gfx[gfx.index("bool GraphicsPipeline::ConfigureDraw("):set_start]
assert "#ifdef PS5_NATIVE\n    // Descriptor-set updates are encoded" in gfx
assert gfx.index("    scheduler.Record([this, descriptor_data", set_start) < gfx.rindex(
    "last_descriptor_payload.assign(entries, entries + num_descriptor_entries);")
assert "Zero-descriptor shaders must not pass a null vector pointer" in oracle
host_source=r"""
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#include <cstddef>
struct DescriptorUpdateEntry { std::uint64_t bits; };
struct Ring { std::uint64_t gen=1; std::uint64_t CurrentGeneration() const { return gen; } };
struct Case {
    std::vector<DescriptorUpdateEntry> last_descriptor_payload;
    std::size_t num_descriptor_entries{};
    std::uint64_t last_descriptor_buffer_generation{};
    Ring descriptor_buffer_ring;
    bool bind_pipeline{};
    bool Reuse(const DescriptorUpdateEntry* entries) {
""" + reuse_stmt + r"""
        return reuse_allocation;
    }
    bool NeedsSetUpdate(const DescriptorUpdateEntry* entries) {
        bool update_descriptors=false;
""" + update_stmt + r"""
        return update_descriptors;
    }
    void SaveBuffer(const DescriptorUpdateEntry* entries) {
""" + buffer_snapshot + r"""
    }
    void SaveSet(const DescriptorUpdateEntry* entries) {
        bool update_descriptors=true;
""" + set_snapshot + r"""
    }
};
int main() {
    Case x;
    // First use must allocate, despite an empty payload.
    assert(!x.Reuse(nullptr));
    x.last_descriptor_buffer_generation=1;
    assert(x.Reuse(nullptr));
    assert(!x.NeedsSetUpdate(nullptr));
    x.bind_pipeline=true;
    assert(x.NeedsSetUpdate(nullptr));
    x.bind_pipeline=false;
    x.last_descriptor_payload.push_back({17});
    x.SaveBuffer(nullptr);
    assert(x.last_descriptor_payload.empty());
    x.last_descriptor_payload.push_back({18});
    x.SaveSet(nullptr);
    assert(x.last_descriptor_payload.empty());
    x.num_descriptor_entries=1;
    const DescriptorUpdateEntry a[]{ {123} };
    const DescriptorUpdateEntry b[]{ {124} };
    assert(!x.Reuse(a));
    assert(x.NeedsSetUpdate(a));
    x.SaveBuffer(a);
    assert(x.Reuse(a));
    assert(!x.Reuse(b));
    assert(x.NeedsSetUpdate(b));
    x.SaveSet(b);
    assert(x.Reuse(b));
    assert(!x.NeedsSetUpdate(b));
}
"""
with tempfile.TemporaryDirectory(prefix="encore-empty-payload-") as folder:
    cpp=Path(folder)/"test.cpp"
    cpp.write_text(host_source)
    for opt in ("-O0","-O2"):
        exe=Path(folder)/("payload"+opt)
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined",str(cpp),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("ENCORE_EMPTY_DESCRIPTOR_PAYLOAD_PASS",opt)
