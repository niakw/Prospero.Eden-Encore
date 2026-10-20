#!/usr/bin/env python3
"""The first generated quad-index LUT needs no fence for an absent old VkBuffer."""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cost = (root / "vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
oracle = (root / "tools/prepare-vulkan-port.py").read_text()
wrapper = (root / "vendor/sources/eden/src/video_core/vulkan_common/vulkan_wrapper.h").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
upstream = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_buffer_cache.cpp").read_text()
assert "explicit operator bool() const noexcept {\n        return handle != VkBuffer{};" in wrapper
assert "void UpdateBuffer(u32 num_indices_)" in cost
start = cost.index("void UpdateBuffer(u32 num_indices_)")
end = cost.index("\n    void BindBuffer(",start)
method = cost[start:end]
assert method.count("scheduler.Finish();") == 1
assert method.index("if (num_indices_ <= num_indices)") < method.index("if (buffer)")
assert method.index("if (buffer)") < method.index("scheduler.Finish();") < method.index(
    "num_indices = num_indices_;")
assert method.count("memory_allocator.CreateBuffer(") == 1
assert "buffer = memory_allocator.CreateBuffer(" in method
assert "scheduler.Record([src_buffer = staging.buffer" in method
assert "const bool host_visible = buffer.IsHostVisible();" in method
assert "void UpdateBuffer(u32 num_indices_)" in upstream
assert "        scheduler.Finish();" in upstream
assert "python3 -B tools/check-ps5-quad-index-initial-fence-host.py" in workflow

# Confirm the guarded form is exactly an adapter applied after the existing
# VulkanTimer(7) instrumentation (unchanged exact upstream wait-site count).
gen=ast.parse(oracle)
# Locate the dict by its stable Vulkan source key, not the variable name
# used for the generator's performance probes.
# Another independently-owned deferred-copy dictionary now contains the
# same file key. Resolve the source-rewrite table by the actual LUT-fence
# invariant, rather than incorrectly requiring that file key to be unique.
tables=[node for node in ast.walk(gen) if isinstance(node,ast.Dict)
        and any(isinstance(key,ast.Constant) and key.value=="vk_buffer_cache"
                for key in node.keys)]
guard_tables=[]
for table in tables:
    entry=next(v for k,v in zip(table.keys,table.values)
               if isinstance(k,ast.Constant) and k.value=="vk_buffer_cache")
    pairs=[ast.literal_eval(n) for n in entry.elts
           if isinstance(n,ast.Tuple) and len(n.elts)==2]
    matching=[(before,after) for before,after in pairs if "very first LUT" in after]
    if matching:
        guard_tables.append(matching)
assert len(guard_tables)==1
guarded=guard_tables[0]
assert len(guarded)==1
before,after=guarded[0]
assert before.count("scheduler.Finish();")==after.count("scheduler.Finish();")==1
assert before in cost.replace(after,before)
assert after in cost
assert "('vk_buffer_cache', 7, 3)" in oracle

# Reuse the source EXACT guard in an independent host fixture. No GPU is
# needed to prove an absent VkBuffer requires no lifetime fence.
guard=after[after.index("        if (buffer) {"):after.index("\n\n        num_indices",after.index("        if (buffer) {"))]
cpp=r"""
#include <cassert>
#include <cstdint>
using u32=std::uint32_t;
namespace Eden::Performance {
struct VulkanTimer {explicit VulkanTimer(int) {} ~VulkanTimer() {}};
}
struct Scheduler {
    unsigned finishes=0;
    void Finish() {++finishes;}
};
struct Buffer {
    bool valid=false;
    explicit operator bool() const noexcept {return valid;}
};
struct LUT {
    Buffer buffer{};
    u32 num_indices=0;
    Scheduler& scheduler;
    void UpdateBuffer(u32 num_indices_) {
        if (num_indices_ <= num_indices) return;
__GUARD__
        num_indices=num_indices_;
        buffer.valid=true; // the newly created VkBuffer
    }
};
int main() {
    Scheduler scheduler;
    LUT lut{{},0,scheduler};
    lut.UpdateBuffer(16);
    assert(scheduler.finishes==0 && lut.num_indices==16);
    lut.UpdateBuffer(8);
    assert(scheduler.finishes==0 && lut.num_indices==16);
    lut.UpdateBuffer(32);
    assert(scheduler.finishes==1 && lut.num_indices==32);
    lut.UpdateBuffer(32);
    assert(scheduler.finishes==1);
    LUT second{{},0,scheduler};
    second.UpdateBuffer(128);
    assert(scheduler.finishes==1);
    second.UpdateBuffer(256);
    assert(scheduler.finishes==2);
}
""".replace("__GUARD__",guard)
cc=shutil.which("clang++-18") or shutil.which("clang++")
assert cc, "Clang is required"
with tempfile.TemporaryDirectory(prefix="encore-quad-lut-fence-") as temp:
    src=Path(temp)/"case.cpp";binary=Path(temp)/"case"
    src.write_text(cpp)
    subprocess.run([cc,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(binary)],check=True,timeout=45)
    subprocess.run([str(binary)],check=True,timeout=30)
print("QUAD_INDEX_INITIAL_FENCE_HOST_PASS first_no_wait=2 resize_wait=2 stable_no_wait=2")
