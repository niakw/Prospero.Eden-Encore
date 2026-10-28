#!/usr/bin/env python3
"""Source-extracted first-use descriptor snapshot allocation witness.

The selected GPU owner preflights storage before paired guest-cache locks.
A guarded allocator proves that the subsequent descriptor snapshot writes
do not allocate under that lock; original, un-preflighted behavior must fail.
This is a host correctness/critical-section proof, NOT console FPS evidence.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = (ROOT / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
GENERATOR = (ROOT / "tools/prepare-vulkan-port.py").read_text()
RASTER = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()

def extract(src, signature):
    assert src.count(signature) == 1
    pos = src.index(signature)
    first = src.index("{", pos)
    depth = 0
    for j in range(first, len(src)):
        depth += (src[j] == "{") - (src[j] == "}")
        if depth == 0:
            return src[pos:j+1]
    raise AssertionError("unbalanced body")

signature = "void GraphicsPipeline::PreflightDescriptorScratch() {"
method = extract(NATIVE, signature)
assert "void PreflightDescriptorScratch();" in GENERATOR
assert signature in GENERATOR
assert "last_descriptor_payload.reserve(num_descriptor_entries);" in GENERATOR
assert "last_descriptor_payload.reserve(num_descriptor_entries);" in method
# The native selected implementation must be identical to the generator's
# complete C++ body, not merely contain the expected marker.
assert method.replace("\n", r"\n") in GENERATOR, "maintained pipeline preflight drifted from staging"
assert "if (scratch.in_use) return;" in method
assert "last_descriptor_payload.capacity() < num_descriptor_entries" in method
assert RASTER.index("pipeline->PreflightDescriptorScratch();") < RASTER.index(
    "std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};"
)
# Descriptor reads and vector writes still execute under the paired locks.
assert NATIVE.index("last_descriptor_payload.assign(entries, entries + num_descriptor_entries)") > (
    NATIVE.index("bool GraphicsPipeline::ConfigureDraw(")
)
# All three real snapshots must be preflighted before paired cache locks:
# descriptor-buffer, desktop legacy, and PS5's post-Record legacy commit.
assert NATIVE.count("last_descriptor_payload.assign(entries, entries + num_descriptor_entries)") == 3
configure = NATIVE[NATIVE.index("bool GraphicsPipeline::ConfigureDraw("):]
record_at = configure.index("    scheduler.Record([this, descriptor_data")
assert configure.count("last_descriptor_payload.assign(entries, entries + num_descriptor_entries)") == 3
assert configure.index("#ifndef PS5_NATIVE") < record_at
assert configure.index("#ifdef PS5_NATIVE\n    // Descriptor-set updates are encoded") > record_at

# Recreate the exact previous selected preflight from the reviewed delta.
snapshot_guard = """
    // Allocate the per-pipeline descriptor snapshot BEFORE the buffer/texture
    // cache mutex pair. ConfigureDraw still reads, compares and publishes the
    // actual guest descriptors only after taking both locks.
    if (num_descriptor_entries != 0 && descriptor_set_layout &&
        (uses_descriptor_buffer || !uses_push_descriptor) &&
        last_descriptor_payload.capacity() < num_descriptor_entries) {
        last_descriptor_payload.reserve(num_descriptor_entries);
    }
"""
assert method.count(snapshot_guard) == 1
prior = method.replace(snapshot_guard, "").replace(
    "GraphicsPipeline::PreflightDescriptorScratch()", "GraphicsPipeline::OldPreflight()"
)
assert prior != method

mock = r"""
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <vector>

inline bool cache_pair_locked = false;
inline unsigned cache_pair_allocator_attempts = 0;
template<typename T>
struct GuardedAllocator {
    using value_type = T;
    GuardedAllocator() = default;
    template<typename U> GuardedAllocator(const GuardedAllocator<U>&) {}
    T* allocate(std::size_t n) {
        if (cache_pair_locked) {
            ++cache_pair_allocator_attempts;
            throw std::logic_error("ALLOC_DURING_CACHE_PAIR");
        }
        return std::allocator<T>{}.allocate(n);
    }
    void deallocate(T* p, std::size_t n) {
        std::allocator<T>{}.deallocate(p,n);
    }
};
struct Scratch {
    bool in_use{};
    std::vector<int> views, samplers;
};
static thread_local Scratch graphics_descriptor_scratch{};
static thread_local Scratch graphics_descriptor_nested_scratch{};
struct GraphicsPipeline {
    std::size_t num_image_elements{}, num_textures{}, num_descriptor_entries{};
    bool descriptor_set_layout{}, uses_descriptor_buffer{}, uses_push_descriptor{};
    std::vector<int, GuardedAllocator<int>> last_descriptor_payload;
    void PreflightDescriptorScratch();
    void OldPreflight();
};
"""
checks = r"""
void update_snapshot(GraphicsPipeline& pipeline, unsigned elements) {
    std::vector<int> descriptors(elements, 24);
    // ConfigureDraw is called with both guest cache mutexes held.
    const auto data = pipeline.last_descriptor_payload.data();
    cache_pair_locked = true;
    pipeline.last_descriptor_payload.assign(descriptors.begin(), descriptors.end());
    cache_pair_locked = false;
    assert(pipeline.last_descriptor_payload.data() == data);
}
int main() {
    GraphicsPipeline pipeline;
    pipeline.num_image_elements = 13;
    pipeline.num_textures = 8;
    pipeline.num_descriptor_entries = 16;
    pipeline.descriptor_set_layout = true;
    pipeline.uses_descriptor_buffer = true;
    pipeline.PreflightDescriptorScratch();
    assert(graphics_descriptor_scratch.views.capacity() >= 13);
    assert(graphics_descriptor_scratch.samplers.capacity() >= 8);
    assert(pipeline.last_descriptor_payload.capacity() >= 16);
    update_snapshot(pipeline, 16);
    pipeline.PreflightDescriptorScratch();
    update_snapshot(pipeline, 16);

    // Descriptor sets (as opposed to descriptor buffers) also snapshot data.
    GraphicsPipeline set_pipeline;
    set_pipeline.num_descriptor_entries = 4;
    set_pipeline.descriptor_set_layout = true;
    set_pipeline.PreflightDescriptorScratch();
    assert(set_pipeline.last_descriptor_payload.capacity() >= 4);
    update_snapshot(set_pipeline, 4);

    // Push-descriptor-only pipelines do not use this snapshot.
    GraphicsPipeline push_pipeline;
    push_pipeline.num_descriptor_entries = 4;
    push_pipeline.descriptor_set_layout = true;
    push_pipeline.uses_push_descriptor = true;
    push_pipeline.PreflightDescriptorScratch();
    assert(push_pipeline.last_descriptor_payload.capacity() == 0);

    GraphicsPipeline empty;
    empty.descriptor_set_layout = true;
    empty.uses_descriptor_buffer = true;
    empty.PreflightDescriptorScratch();
    assert(empty.last_descriptor_payload.capacity() == 0);

    // Nested shader work uses private scratch, without touching the first
    // draw's scratch. The descriptor payload reservation remains per pipeline.
    graphics_descriptor_scratch.in_use = true;
    GraphicsPipeline nested;
    nested.num_image_elements = 7;
    nested.num_textures = 3;
    nested.num_descriptor_entries = 5;
    nested.descriptor_set_layout = true;
    nested.uses_descriptor_buffer = true;
    nested.PreflightDescriptorScratch();
    assert(graphics_descriptor_nested_scratch.views.capacity() >= 7);
    assert(nested.last_descriptor_payload.capacity() >= 5);
    update_snapshot(nested, 5);
    graphics_descriptor_scratch.in_use = false;
    const unsigned maintained_locked_allocations = cache_pair_allocator_attempts;
    assert(maintained_locked_allocations == 0);

    // The old implementation didn't reserve last_descriptor_payload before
    // locking the caches. Our guarded allocator catches its first allocation.
    GraphicsPipeline old;
    old.num_descriptor_entries = 16;
    old.descriptor_set_layout = true;
    old.uses_descriptor_buffer = true;
    old.OldPreflight();
    assert(old.last_descriptor_payload.capacity() == 0);
    cache_pair_locked = true;
    bool rejected = false;
    try {
        old.last_descriptor_payload.assign(16, 12);
    } catch (const std::logic_error&) {
        rejected = true;
    }
    cache_pair_locked = false;
    assert(rejected);
    assert(cache_pair_allocator_attempts == maintained_locked_allocations + 1);
    std::printf("F01_PAYLOAD_ALLOCATION_FIXTURE prior_under_lock=%u "
                "maintained_under_lock=%u scope=host_mock\n",
                cache_pair_allocator_attempts - maintained_locked_allocations,
                maintained_locked_allocations);
    std::puts("GPU_DESCRIPTOR_PAYLOAD_PREFLIGHT_PASS");
}
"""
program = mock + method + "\n\n" + prior + "\n\n" + checks
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-gpu-payload-preflight-") as folder:
    cpp = Path(folder) / "main.cpp"
    cpp.write_text(program)
    for opt in ("-O0", "-O2"):
        exe = Path(folder) / ("test" + opt)
        build = subprocess.run([
            compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            str(cpp), "-o", str(exe),
        ], capture_output=True, text=True, timeout=45)
        assert build.returncode == 0, build.stderr[-4000:]
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, (run.stdout, run.stderr[-4000:])
        assert "GPU_DESCRIPTOR_PAYLOAD_PREFLIGHT_PASS" in run.stdout
        expected = ("F01_PAYLOAD_ALLOCATION_FIXTURE prior_under_lock=1 "
                    "maintained_under_lock=0 scope=host_mock")
        assert expected in run.stdout, (opt, run.stdout)
        print(expected, opt, flush=True)
        print("GPU_DESCRIPTOR_PAYLOAD_PREFLIGHT_PASS", opt, "allocation-before-pair")
