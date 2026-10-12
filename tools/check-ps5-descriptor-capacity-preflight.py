#!/usr/bin/env python3
"""R363: source-extracted host contract for guaranteed-only Vulkan ring preflight."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active/eden-vulkan"
ring = (active / "vulkan_descriptor_buffer.cpp").read_text()
cost = (active / "vk_descriptor_buffer_cost.cpp").read_text()
header = (active / "include/video_core/renderer_vulkan/vk_descriptor_buffer.h").read_text()
pipeline = (active / "include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
raster = (active / "vulkan_rasterizer.cpp").read_text()
oracle = (root / "tools/prepare-vulkan-port.py").read_text()

def method(text, signature):
    begin = text.index(signature)
    opened = text.index("{", begin)
    level = 0
    for i in range(opened, len(text)):
        if text[i] == "{": level += 1
        elif text[i] == "}":
            level -= 1
            if level == 0:
                return text[begin:i+1]
    raise AssertionError("unterminated method")

preflight = method(ring, "bool DescriptorBufferRing::PreflightCapacity(")
getter = method(pipeline, "[[nodiscard]] VkDeviceSize DescriptorRingPreflightSize() const")
assert "PreflightCapacity(Scheduler& scheduler, VkDeviceSize size)" in header
assert "if (chunks.empty() || frame_reused || size == 0 || !CanAllocate(size))" in preflight
assert "needed <= chunk_capacity - cursor || chunk_cursor + 1 < chunks_per_frame" in preflight
assert "scheduler.Finish();" in preflight
assert preflight.index("scheduler.Finish();") < preflight.index("++generation;")
assert "DescriptorRingPreflightSize()" in raster
assert raster.index("descriptor_buffer_ring.PreflightCapacity(") < raster.index(
    "std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};")
assert "gpu_memory->FlushCaching();\n        pipeline = pipeline_cache.CurrentGraphicsPipeline();" in raster
assert "DescriptorRingPreflightSize()" in oracle
assert "PreflightCapacity(Scheduler& scheduler" in oracle
assert "('vk_descriptor_buffer', 10, 4)" in oracle
assert "scheduler.Finish();" in cost  # existing exact fallback is NOT removed
assert "DescriptorRingFinish" in cost
assert "DescriptorRingPreflight" in cost
assert "DescriptorRingPreflight" in oracle

# These are actual versioned method bodies, not a hand-written parallel
# algorithm. The fake GPU scheduler asserts Finish is not inside cache locks.
cpp = r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using u64 = std::uint64_t;
using VkDeviceSize = std::uint64_t;
namespace Common {
template<typename T>
T AlignUp(T n, T a) { return (n + a - 1) / a * a; }
}
static bool cache_locks_held = false;
struct Scheduler {
    int finishes = 0;
    void Finish() { assert(!cache_locks_held); ++finishes; }
};
class DescriptorBufferRing {
public:
    bool PreflightCapacity(Scheduler&, VkDeviceSize);
    [[nodiscard]] bool CanAllocate(VkDeviceSize s) const {
        return Common::AlignUp(s, alignment) <= chunk_capacity;
    }
    [[nodiscard]] u64 CurrentGeneration() const noexcept { return generation; }
    std::vector<int> chunks{1,2};
    bool frame_reused = false;
    VkDeviceSize alignment = 4;
    VkDeviceSize chunk_capacity = 100;
    size_t chunk_cursor = 0, chunks_per_frame = 2;
    VkDeviceSize cursor = 0;
    u64 generation = 8;
};
struct DescriptorBufferLayout { VkDeviceSize size = 16; };
struct Pipeline {
    DescriptorBufferRing& descriptor_buffer_ring;
    bool uses_descriptor_buffer = true;
    int descriptor_set_layout = 1;
    size_t num_descriptor_entries = 4;
    std::vector<int> last_descriptor_payload{1,2,3,4};
    u64 last_descriptor_buffer_generation = 0;
    DescriptorBufferLayout descriptor_buffer_layout{};
    [[nodiscard]] bool CanUseDescriptorBuffer() const noexcept {
        return uses_descriptor_buffer && descriptor_set_layout;
    }
__GETTER__
};
__METHOD__
int main() {
    Scheduler s;
    DescriptorBufferRing r;
    Pipeline p{r};
    // Known old descriptor payload shape/gen or no extension: no pre-drain.
    p.last_descriptor_buffer_generation = r.generation;
    assert(p.DescriptorRingPreflightSize() == 0);
    p.last_descriptor_payload.pop_back();
    assert(p.DescriptorRingPreflightSize() == 16);
    p.last_descriptor_payload.push_back(4);
    p.last_descriptor_buffer_generation = 7;
    assert(p.DescriptorRingPreflightSize() == 16);
    p.uses_descriptor_buffer = false;
    assert(p.DescriptorRingPreflightSize() == 0);
    p.uses_descriptor_buffer = true;
    // Normal frames, exact fit, or another available chunk: no extra waits.
    r.cursor = 84;
    assert(!r.PreflightCapacity(s, 16) && s.finishes == 0);
    r.cursor = 88;
    assert(!r.PreflightCapacity(s, 12) && s.finishes == 0);
    assert(!r.PreflightCapacity(s, 16) && s.finishes == 0);
    r.chunk_cursor = 1;
    r.cursor = 88;
    // The old code's guaranteed drain now occurs BEFORE both guest locks.
    assert(p.DescriptorRingPreflightSize() == 16);
    assert(r.PreflightCapacity(s, p.DescriptorRingPreflightSize()));
    assert(s.finishes == 1 && r.cursor == 0 && r.chunk_cursor == 0);
    assert(r.generation == 9);
    assert(p.DescriptorRingPreflightSize() == 16); // old offset now invalid
    cache_locks_held = true;  // new allocation safely occurs after lock acquire
    cache_locks_held = false;
    assert(!r.PreflightCapacity(s, 16) && s.finishes == 1);
    // No preflight if frame reuse is pending, memory absent, payload
    // larger than one chunk or size 0; Allocate's original fallback stays.
    r.cursor = 99; r.chunk_cursor = 1;
    r.frame_reused = true;
    assert(!r.PreflightCapacity(s, 16));
    r.frame_reused = false;
    assert(!r.PreflightCapacity(s, 0));
    assert(!r.PreflightCapacity(s, 104));
    r.chunks.clear();
    assert(!r.PreflightCapacity(s, 16));
    assert(s.finishes == 1 && r.generation == 9);
    // A certain one-time draw does NOT require a drain when there is room.
    r.chunks.push_back(1);
    r.cursor = 96; r.chunk_cursor = 1;
    assert(r.PreflightCapacity(s, 8) && s.finishes == 2 && r.generation == 10);
}
""".replace("__GETTER__", getter).replace("__METHOD__", preflight)
env = os.environ.copy()
if sys.platform == "darwin" and not env.get("SDKROOT"):
    old = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
    if old.is_dir(): env["SDKROOT"] = str(old)
with tempfile.TemporaryDirectory(prefix="eden-r363-ring-") as d:
    source = Path(d) / "ring.cpp"
    out = Path(d) / "ring"
    source.write_text(cpp)
    compiler = "c++"
    subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(source), "-o", str(out)],
                   check=True, env=env, timeout=30)
    subprocess.run([str(out)], check=True, env=env, timeout=15)
print("PASS R363 source-extracted preflight: definite misses, capacity, frame reuse, fencing, generations")
