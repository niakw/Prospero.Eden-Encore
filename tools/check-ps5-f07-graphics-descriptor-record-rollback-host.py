#!/usr/bin/env python3
"""F07: graphics legacy descriptors must not cache an unsubmitted HUD draw."""
from pathlib import Path
import shutil, subprocess, tempfile

root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
scope=src[src.index("GraphicsPipeline::ConfigureDraw("):src.index("GraphicsPipeline::~GraphicsPipeline()")]
start=scope.index("    bool update_descriptors = true;")
before=scope[start:scope.index("    scheduler.Record([this, descriptor_data",start)]
post_start=scope.index("#ifdef PS5_NATIVE\n    // Descriptor-set updates are encoded")
post_end=scope.index("#endif",post_start)+len("#endif")
after=scope[post_start:post_end]
assert "#ifndef PS5_NATIVE" in before
assert "last_descriptor_payload.assign(entries, entries + num_descriptor_entries)" in before
assert "last_descriptor_payload.assign(entries, entries + num_descriptor_entries)" in after
assert scope.index("    scheduler.Record([this, descriptor_data") < post_start
assert scope.index("    scheduler.Record([this, descriptor_data") > scope.index("#ifndef PS5_NATIVE")
assert "F07 defer PS5 legacy descriptor memo until accepted Vulkan draw" in generator
assert "F07 publish PS5 legacy descriptor memo after accepted Vulkan draw" in generator
for wf in (".github/workflows/encore-core-fast-gate.yml",
           ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-graphics-descriptor-record-rollback-host.py" in (root/wf).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <vector>
using DescriptorUpdateEntry = std::uint64_t;
struct Probe {
    bool descriptor_set_layout{true};
    bool uses_push_descriptor{};
    bool uses_descriptor_buffer{};
    bool bind_pipeline{};
    std::size_t num_descriptor_entries{1};
    std::vector<DescriptorUpdateEntry> last_descriptor_payload{};
    std::vector<DescriptorUpdateEntry> descriptors{2};
    unsigned accepted{};
    bool Submit(bool refuse) {
        const void* descriptor_data = descriptors.data();
""" + before + r"""
        if (refuse) throw std::runtime_error("queue refused");
        ++accepted;
""" + after + r"""
        return update_descriptors;
    }
};
int main() {
    Probe p{};
    bool fail=false;
    try { p.Submit(true); } catch (const std::runtime_error&) { fail=true; }
    assert(fail && p.accepted==0);
#ifdef PS5_NATIVE
    assert(p.last_descriptor_payload.empty());
    assert(p.Submit(false));
#else
    assert(p.last_descriptor_payload.size()==1 && p.last_descriptor_payload[0]==2);
    assert(!p.Submit(false));
#endif
    assert(p.accepted==1 && p.last_descriptor_payload[0]==2);
    assert(!p.Submit(false));
    p.descriptors[0]=3;
    fail=false;
    try { p.Submit(true); } catch (const std::runtime_error&) { fail=true; }
    assert(fail && p.accepted==2);
#ifdef PS5_NATIVE
    assert(p.last_descriptor_payload[0]==2);
    assert(p.Submit(false));
#else
    assert(p.last_descriptor_payload[0]==3);
    assert(!p.Submit(false));
#endif
    assert(p.last_descriptor_payload[0]==3 && p.accepted==3);
    assert(!p.Submit(false));
    // Empty layouts must not read descriptor_data while still marking
    // an accepted bind as done, and a later changed count must retry.
    Probe empty{};
    empty.num_descriptor_entries=0;
    empty.bind_pipeline=true;
    assert(empty.Submit(false));
    empty.bind_pipeline=false;
    assert(empty.last_descriptor_payload.empty());
    empty.num_descriptor_entries=1;
    assert(empty.Submit(false));
    assert(empty.last_descriptor_payload.size()==1);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-descriptor-record-") as temp:
    source=Path(temp)/"test.cpp"
    source.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            out=Path(temp)/(("ps5" if native else "desktop")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *flags,str(source),"-o",str(out)],
                                  capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            run=subprocess.run([str(out)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_GRAPHICS_DESCRIPTOR_RECORD_PASS PS5_rejected_payload_uncached=1 retry=1 unchanged=1 empty=1 desktop_original=1 O0=1 O2=1 UBSan=1")
