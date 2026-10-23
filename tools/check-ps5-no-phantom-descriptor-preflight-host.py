#!/usr/bin/env python3
"""Source-extracted native graphics/compute descriptor preflight regression.

Compile all six maintained conditional sites. Empty-descriptor draws MUST NOT
submit a speculative 1024-entry queue preflight, while real descriptor users
still drain before cache locks and reselect their pipeline after a wait.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
graphics_start = native.index("void RasterizerVulkan::PrepareDraw(")
compute_start = native.index("void RasterizerVulkan::DispatchCompute(")
graphics = native[graphics_start:compute_start]
compute = native[compute_start:]
loop_marker = "for (unsigned preflight = 0; preflight != 2; ++preflight) {"
if_marker = ("if (pipeline->HasDescriptorEntries() &&\n"
             "            guest_descriptor_queue.PreflightLargeGuestDraw(")

assert native.count("if (!pipeline->HasDescriptorEntries() ||") == 2
assert native.count(if_marker) == 4
assert generator.count("if (!pipeline->HasDescriptorEntries() ||") == 2
assert generator.count("if (pipeline->HasDescriptorEntries() &&") == 4
assert native.count("AcquireKnownEmpty(uses_descriptor_buffer)") == 2 or (
    "AcquireKnownEmpty(uses_descriptor_buffer)" in
    (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
)
assert "if (pipeline->HasDescriptorEntries() &&" in graphics
assert "if (pipeline->HasDescriptorEntries() &&" in compute

def extract_block(source: str, begin: int, opening: int) -> str:
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[begin:pos + 1]
    raise AssertionError("Unbalanced native preflight block")

def extract_loop(source: str) -> str:
    assert source.count(loop_marker) == 1
    start = source.index(loop_marker)
    return extract_block(source, start, source.index("{", start))

def extract_guards(source: str) -> list[str]:
    assert source.count(if_marker) == 2
    found = []
    offset = 0
    while True:
        start = source.find(if_marker, offset)
        if start < 0:
            break
        # The callback has a lambda body; skip that brace and find the actual
        # if-body opening brace after the reservation expression.
        after_reservation = source.index("DescriptorEntryReservation())) {", start)
        opening = source.index("{", after_reservation)
        found.append(extract_block(source, start, opening))
        offset = opening + 1
    return found

graph_loop = extract_loop(graphics)
compute_loop = extract_loop(compute)
graph_guards = extract_guards(graphics)
compute_guards = extract_guards(compute)
for block in [graph_loop, compute_loop, *graph_guards, *compute_guards]:
    assert "pipeline->HasDescriptorEntries()" in block
    assert "PreflightLargeGuestDraw" in block
    assert "gpu_memory->FlushCaching()" in block

host = r"""
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <functional>
#include <utility>
namespace Eden::Performance {
    enum class GraphicsDrawDrop { NoPipeline };
    inline void RecordGraphicsDrawDrop(GraphicsDrawDrop) {}
}
struct Pipeline {
    bool descriptors{false};
    bool HasDescriptorEntries() const { return descriptors; }
    std::size_t DescriptorEntryReservation() const {
        return descriptors ? 17 : 0x400;
    }
};
struct Scheduler {
    int waits{};
    std::function<void()> on_wait;
    void WaitWorker() {
        ++waits;
        if (on_wait) on_wait();
    }
};
struct DescriptorQueue {
    int calls{};
    int phantom{};
    template<typename Callback>
    bool PreflightLargeGuestDraw(Callback&& cb, std::size_t entries) {
        ++calls;
        if (entries == 0x400) ++phantom;
        cb();
        return true;
    }
};
struct GpuMemory {
    int flushes{};
    void FlushCaching() { ++flushes; }
};
struct Cache {
    Pipeline* selected{};
    int selections{};
    Pipeline* CurrentGraphicsPipeline() { ++selections; return selected; }
    Pipeline* CurrentComputePipeline() { ++selections; return selected; }
};
struct Rig {
    Pipeline full{true}, empty{false};
    Pipeline* pipeline{};
    DescriptorQueue guest_descriptor_queue;
    Scheduler scheduler;
    GpuMemory memory;
    GpuMemory* gpu_memory{&memory};
    Cache pipeline_cache;
    explicit Rig(bool has_entries, bool switch_after_wait = false) {
        pipeline = has_entries ? &full : &empty;
        pipeline_cache.selected = pipeline;
        if (switch_after_wait) scheduler.on_wait = [this] {
            pipeline_cache.selected = &empty;
        };
    }
    void GraphLoop() { GRAPH_LOOP }
    void GraphReuse() { GRAPH_REUSE }
    void GraphCapacity() { GRAPH_CAPACITY }
    void ComputeLoop() { COMPUTE_LOOP }
    void ComputeReuse() { COMPUTE_REUSE }
    void ComputeCapacity() { COMPUTE_CAPACITY }
};
using Method = void (Rig::*)();
void scenario(Method fn) {
    // Descriptor-free pipelines don't write guest descriptors. In the old
    // source all six checks passed the phantom 1024 entry reservation.
    Rig empty{false};
    (empty.*fn)();
    assert(empty.guest_descriptor_queue.calls == 0);
    assert(empty.guest_descriptor_queue.phantom == 0);
    assert(empty.scheduler.waits == 0);

    // Nonempty pipelines keep both the normal drain and reselection path.
    Rig full{true};
    (full.*fn)();
    assert(full.guest_descriptor_queue.calls >= 1);
    assert(full.guest_descriptor_queue.phantom == 0);
    assert(full.scheduler.waits >= 1);
    assert(full.pipeline_cache.selections >= 1);

    // A real WaitWorker may publish a new descriptor-free guest shader.
    // Subsequent native preflight must not fall back to a phantom drain.
    Rig changed{true, true};
    (changed.*fn)();
    assert(changed.guest_descriptor_queue.calls == 1);
    assert(changed.guest_descriptor_queue.phantom == 0);
    assert(changed.scheduler.waits == 1);
    assert(changed.pipeline == &changed.empty);
}
int main() {
    for (Method fn : {
        &Rig::GraphLoop, &Rig::GraphReuse, &Rig::GraphCapacity,
        &Rig::ComputeLoop, &Rig::ComputeReuse, &Rig::ComputeCapacity
    }) scenario(fn);
    std::puts("EMPTY_DESCRIPTOR_SIX_NATIVE_PREFLIGHT_SITES_PASS");
}
"""
for placeholder, body in [
    ("GRAPH_LOOP", graph_loop),
    ("GRAPH_REUSE", graph_guards[0]),
    ("GRAPH_CAPACITY", graph_guards[1]),
    ("COMPUTE_LOOP", compute_loop),
    ("COMPUTE_REUSE", compute_guards[0]),
    ("COMPUTE_CAPACITY", compute_guards[1]),
]:
    assert host.count(placeholder) == 1
    host = host.replace(placeholder, body)

# The real native code calls CurrentGraphicsPipeline/CurrentComputePipeline
# after waiting. A declaration here is enough to instantiate the real blocks.
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "No host C++ compiler available"
with tempfile.TemporaryDirectory(prefix="encore-no-phantom-preflight-") as folder:
    source_file = Path(folder) / "preflight.cpp"
    source_file.write_text(host)
    for opt in ("-O0", "-O2"):
        output = Path(folder) / ("preflight" + opt)
        build = subprocess.run(
            [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
             "-fsanitize=undefined", "-fno-sanitize-recover=all",
             str(source_file), "-o", str(output)],
            capture_output=True, text=True, timeout=45)
        assert build.returncode == 0, (opt, build.stderr[-5000:])
        run = subprocess.run([str(output)], capture_output=True, text=True, timeout=20)
        assert run.returncode == 0, (opt, run.stdout, run.stderr[-5000:])
        assert "EMPTY_DESCRIPTOR_SIX_NATIVE_PREFLIGHT_SITES_PASS" in run.stdout
        print("EMPTY_DESCRIPTOR_PREFLIGHT_SOURCE_PASS", opt)
