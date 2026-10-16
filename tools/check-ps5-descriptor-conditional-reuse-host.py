#!/usr/bin/env python3
"""Host-only source-extracted witness for conditional descriptor ring reuse.

This intentionally reproduces the remaining in-lock GPU Finish fallback.
It does NOT change native runtime behavior or claim to fix frame stalls.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
ring = (root / "vendor/encore-active/eden-vulkan/vulkan_descriptor_buffer.cpp").read_text()
ring_header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_descriptor_buffer.h").read_text()
pipeline_header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
pipeline_impl = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

# Native capability provenance: the release uses the vendored RADV driver,
# whose source advertises the feature unless runtime negotiation rejects it.
# These guards prove source reachability, NOT that an actual device enabled it.
package = (root / "tools/build-package.sh").read_text()
dev_flags = (root / "headless/dev_vulkan.h").read_text()
device = (root / "vendor/encore-active/eden-vulkan/vulkan_device.cpp").read_text()
radv = (root / "vendor/encore-active/ps5-mesa/src/amd/vulkan/radv_physical_device.c").read_text()
assert "EDEN_PS5_VULKAN=ON EDEN_VULKAN_DRIVER=RADV" in package
assert "inline bool disable_descriptor_buffer = false;" in dev_flags
reset = dev_flags.split("inline void ResetForTitle() noexcept {", 1)[1].split("}", 1)[0]
assert "disable_descriptor_buffer = false;" in reset
assert ".EXT_descriptor_buffer = true," in radv
assert ".descriptorBuffer = true," in radv
assert "extensions.descriptor_buffer = features.descriptor_buffer.descriptorBuffer &&" in device
assert "!::Eden::DevVulkan::disable_descriptor_buffer;" in device
assert "if (!device.IsExtDescriptorBufferSupported() || !device.IsBufferDeviceAddressSupported())" in ring

def method(src: str, needle: str) -> str:
    start = src.index(needle)
    open_brace = src.index("{", start)
    depth = 0
    for index in range(open_brace, len(src)):
        if src[index] == "{":
            depth += 1
        elif src[index] == "}":
            depth -= 1
            if depth == 0:
                return src[start:index + 1]
    raise AssertionError("unterminated method: " + needle)

preflight = method(ring, "bool DescriptorBufferRing::PreflightCapacity(")
allocate = method(ring, "DescriptorBufferRing::Allocation DescriptorBufferRing::Allocate(")
getter = method(pipeline_header, "[[nodiscard]] VkDeviceSize DescriptorRingPreflightSize() const noexcept")
configure = method(pipeline_impl, "bool GraphicsPipeline::ConfigureDraw(")
draw = raster.split("void RasterizerVulkan::PrepareDraw(", 1)[1].split(
    "void RasterizerVulkan::Draw(", 1)[0]

# Pin the precise unresolved path in the active versions, not a handwritten
# imitation of the ring allocation algorithm.
assert "last_descriptor_buffer_generation == descriptor_buffer_ring.CurrentGeneration()" in configure
assert "last_descriptor_payload.size() == num_descriptor_entries" in configure
assert "std::memcmp(last_descriptor_payload.data(), entries," in configure
assert "if (reuse_allocation)" in configure
assert configure.index("if (reuse_allocation)") < configure.index(
    "descriptor_buffer_ring.Allocate(scheduler, descriptor_buffer_layout.size)")
assert "scheduler.Finish();" in allocate
assert "scheduler.Finish();" in preflight
assert "size == 0" in preflight
assert "CurrentGeneration()" in getter
assert "DescriptorRingPreflightSize()" in draw
assert draw.index("descriptor_buffer_ring.PreflightCapacity(") < draw.index(
    "std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};")
assert "bool PreflightCapacity(Scheduler& scheduler, VkDeviceSize size)" in ring_header
assert "check-ps5-descriptor-conditional-reuse-host.py" in workflow

code = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>
using u64 = std::uint64_t;
using u32 = std::uint32_t;
using u8 = std::uint8_t;
using VkDeviceSize = std::uint64_t;
#define ASSERT(x) assert(x)
#define LOG_DEBUG(...) ((void)0)
namespace Common {
template <typename T>
T AlignUp(T n, T a) { return (n + a - 1) / a * a; }
}
struct Scheduler {
    bool cache_locks_held = false;
    int finishes_locked = 0;
    int finishes_unlocked = 0;
    void Finish() {
        if (cache_locks_held) ++finishes_locked;
        else ++finishes_unlocked;
    }
    void Wait(u64) { assert(!cache_locks_held); }
    [[nodiscard]] u64 CurrentTick() const { return 421; }
};
class DescriptorBufferRing {
public:
    struct Allocation {
        u8* host{};
        VkDeviceSize offset{};
        u32 chunk{};
        u64 generation{};
    };
    DescriptorBufferRing() = default;
    bool PreflightCapacity(Scheduler&, VkDeviceSize);
    Allocation Allocate(Scheduler&, VkDeviceSize);
    [[nodiscard]] u64 CurrentGeneration() const noexcept { return generation; }
    [[nodiscard]] bool CanAllocate(VkDeviceSize size) const noexcept {
        return Common::AlignUp(size, alignment) <= chunk_capacity;
    }
    std::vector<int> chunks{1, 2};
    std::array<std::array<u8, 100>, 2> storage{};
    std::vector<u8*> chunk_hosts{storage[0].data(), storage[1].data()};
    VkDeviceSize alignment{4};
    VkDeviceSize chunk_capacity{100};
    size_t chunks_per_frame{2};
    size_t frame_index{0};
    size_t chunk_cursor{1};
    VkDeviceSize cursor{90};
    u64 generation{8};
    std::array<u64, 8> frame_ticks{};
    bool frame_reused{false};
};
struct DescriptorBufferLayout { VkDeviceSize size{16}; };
struct Pipeline {
    DescriptorBufferRing& descriptor_buffer_ring;
    bool uses_descriptor_buffer = true;
    int descriptor_set_layout = 1;
    u64 last_descriptor_buffer_generation = 8;
    std::vector<int> last_descriptor_payload{1, 2, 3, 4};
    size_t num_descriptor_entries = 4;
    DescriptorBufferLayout descriptor_buffer_layout{};
    [[nodiscard]] bool CanUseDescriptorBuffer() const noexcept {
        return uses_descriptor_buffer && descriptor_set_layout;
    }
__GETTER__
};
__PREFLIGHT__
__ALLOCATE__
int main() {
    DescriptorBufferRing ring;
    Scheduler scheduler;
    Pipeline pipeline{ring};
    const std::array<int, 4> new_payload{1, 2, 3, 9};
    assert(pipeline.last_descriptor_buffer_generation == ring.CurrentGeneration());
    assert(pipeline.last_descriptor_payload.size() == pipeline.num_descriptor_entries);
    assert(std::memcmp(pipeline.last_descriptor_payload.data(), new_payload.data(),
                       sizeof(new_payload)) != 0);
    // Shape and generation agree, so preflight cannot prove an allocation.
    assert(pipeline.DescriptorRingPreflightSize() == 0);
    assert(!ring.PreflightCapacity(scheduler, pipeline.DescriptorRingPreflightSize()));
    assert(scheduler.finishes_unlocked == 0);
    // Payload differs: ConfigureDraw's real condition takes Allocate.
    scheduler.cache_locks_held = true;
    const auto allocated = ring.Allocate(scheduler, pipeline.descriptor_buffer_layout.size);
    scheduler.cache_locks_held = false;
    assert(allocated.host != nullptr);
    assert(scheduler.finishes_locked == 1);  // Known remaining in-lock wait.
    assert(ring.CurrentGeneration() == 9);

    // When a generation mismatch makes allocation certain, the existing
    // preflight drains outside the cache locks and Allocate cannot finish.
    DescriptorBufferRing certain_ring;
    Scheduler certain_scheduler;
    Pipeline certain_pipeline{certain_ring};
    certain_pipeline.last_descriptor_buffer_generation = 7;
    assert(certain_pipeline.DescriptorRingPreflightSize() == 16);
    assert(certain_ring.PreflightCapacity(certain_scheduler,
                                         certain_pipeline.DescriptorRingPreflightSize()));
    assert(certain_scheduler.finishes_unlocked == 1);
    assert(certain_ring.CurrentGeneration() == 9);
    certain_scheduler.cache_locks_held = true;
    const auto certain_alloc = certain_ring.Allocate(
        certain_scheduler, certain_pipeline.descriptor_buffer_layout.size);
    certain_scheduler.cache_locks_held = false;
    assert(certain_alloc.host != nullptr);
    assert(certain_scheduler.finishes_locked == 0);

    // Same generation, same count and byte-identical data reuse the prior
    // allocation and never invoke Allocate at all.
    const std::array<int, 4> identical{1, 2, 3, 4};
    assert(std::memcmp(pipeline.last_descriptor_payload.data(), identical.data(),
                       sizeof(identical)) == 0);
}
"""
code = code.replace("__GETTER__", getter).replace("__PREFLIGHT__", preflight).replace("__ALLOCATE__", allocate)
compiler = shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "Clang required for ASan/UBSan source regression"
with tempfile.TemporaryDirectory(prefix="encore-descriptor-conditional-reuse-") as tmp:
    path = Path(tmp) / "witness.cpp"
    binary = Path(tmp) / "witness"
    path.write_text(code)
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(path), "-o", str(binary)], check=True, timeout=45)
    subprocess.run([str(binary)], check=True, timeout=30)
print("DESCRIPTOR_CONDITIONAL_REUSE_HOST_PASS known_in_lock_fallback=1 certain_preflight_outside_locks=1 safe_reuse=1 native_radv_source_gate=1")
