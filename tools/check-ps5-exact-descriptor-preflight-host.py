#!/usr/bin/env python3
"""Source-extracted F01 descriptor capacity parity and shader-reselection regression.

Compile the actual generated PreflightExactGuestDraw method together with
all six maintained native graphics/compute reselect checks. Compare with the
old >1024-only helper on a near-full queue. No PS5 FPS claim is implied.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
generator = (root / "tools/prepare-vulkan-port.py").read_text()
native = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
upstream = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_update_descriptor.cpp").read_text()
assert "if (used + reserve >= frame_payload_size)" in upstream
assert "required_entries > 0 ? required_entries : DEFAULT_REQUIRED_ENTRIES" in upstream

signature = ("    template <typename WaitWorker>\n"
             "    [[nodiscard]] bool PreflightExactGuestDraw(")
assert generator.count(signature) == 1
start = generator.index(signature)
end = generator.index("\n    }\n#endif", start) + len("\n    }")
helper = generator[start:end]
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h").read_text()
assert helper in header, "Native maintained header has a stale exact helper"
initial_signature = ("    template <typename WaitWorker>\n"
                     "    [[nodiscard]] bool PreflightGuestDraw(")
assert generator.count(initial_signature) == 1
initial_start = generator.index(initial_signature)
initial_end = generator.index("\n    }\n    template <typename WaitWorker>", initial_start) + len("\n    }")
initial = generator[initial_start:initial_end]
assert initial in header, "Native maintained header has a stale first preflight"
assert "required_entries != 0 ? required_entries : 0x400" in initial
assert "if (used + reserve < frame_payload_size)" in initial
assert native.count("guest_descriptor_queue.PreflightGuestDraw([this] { scheduler.WaitWorker(); },") == 2
assert generator.count("guest_descriptor_queue.PreflightGuestDraw([this] { scheduler.WaitWorker(); },") == 2
assert "if (entries == 0 || entries >= frame_payload_size)" in helper
assert "if (used + entries < frame_payload_size)" in helper
assert "payload_cursor = payload_start;" in helper
prior = helper.replace("PreflightExactGuestDraw", "OldLargePreflightDraw", 1)
before = "if (entries == 0 || entries >= frame_payload_size)"
after = "if (entries <= 0x400 || entries >= frame_payload_size)"
assert prior.count(before) == 1
prior = prior.replace(before, after)

graphics_start = native.index("void RasterizerVulkan::PrepareDraw(")
compute_start = native.index("void RasterizerVulkan::DispatchCompute(")
graphics = native[graphics_start:compute_start]
compute = native[compute_start:]
loop_tag = "for (unsigned preflight = 0; preflight != 2; ++preflight) {"
check_tag = ("if (pipeline->HasDescriptorEntries() &&\n"
             "            guest_descriptor_queue.PreflightExactGuestDraw(")
assert native.count("PreflightExactGuestDraw(") == 6
assert native.count("if (!pipeline->HasDescriptorEntries() ||") == 2
assert native.count(check_tag) == 4
assert "PreflightLargeGuestDraw(" not in native
assert generator.count("PreflightExactGuestDraw(") == 7

def extract(source, start, open_brace):
    depth = 0
    for pos in range(open_brace, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError("Unbalanced source method")

def loop(source):
    assert source.count(loop_tag) == 1
    start = source.index(loop_tag)
    return extract(source, start, source.index("{", start))

def branches(source):
    assert source.count(check_tag) == 2
    out = []
    at = 0
    while (start := source.find(check_tag, at)) >= 0:
        # Skip lambda braces in the callback argument.
        marker = source.index("DescriptorEntryReservation())) {", start)
        opening = source.index("{", marker)
        out.append(extract(source, start, opening))
        at = opening + 1
    return out

gl, cl = loop(graphics), loop(compute)
gb, cb = branches(graphics), branches(compute)
for block in [gl, *gb]:
    # Graphics generation inserts multiline C++ literally.
    assert block in generator, "Graphics native source drifted from generator"
for block in [cl, *cb]:
    # Compute generator uses escaped newline strings in replace clauses.
    assert block.replace("\n", r"\n") in generator, "Compute native source drifted from generator"
for block in [gl, cl, *gb, *cb]:
    assert "HasDescriptorEntries()" in block
    assert "PreflightExactGuestDraw(" in block
    assert "gpu_memory->FlushCaching()" in block

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <functional>
#include <initializer_list>
namespace Eden::Performance {
    enum class GraphicsDrawDrop { NoPipeline };
    inline void RecordGraphicsDrawDrop(GraphicsDrawDrop) {}
}
struct Pipeline {
    std::size_t descriptors{};
    bool HasDescriptorEntries() const { return descriptors != 0; }
    std::size_t DescriptorEntryReservation() const {
        return descriptors != 0 ? descriptors : 0x400;
    }
};
struct Scheduler {
    int waits{};
    std::function<void()> after_wait;
    void WaitWorker() {
        ++waits;
        if (after_wait) after_wait();
    }
};
struct Queue {
    static constexpr std::size_t frame_payload_size = 4096;
    char storage[frame_payload_size]{};
    char* payload_start{storage};
    char* payload_cursor{storage};
__INITIAL_METHOD__
HELPER
OLD_HELPER
};
struct GpuMemory {
    int flushes{};
    void FlushCaching() { ++flushes; }
};
struct Cache {
    Pipeline* selected{};
    Pipeline* CurrentGraphicsPipeline() { return selected; }
    Pipeline* CurrentComputePipeline() { return selected; }
};
struct Rig {
    Pipeline empty{0}, one{1}, many{2048};
    Pipeline* pipeline{};
    bool initial_descriptor_drain{true}; // Isolated graph-loop witness starts after a real drain.
    Queue guest_descriptor_queue;
    Scheduler scheduler;
    GpuMemory memory;
    GpuMemory* gpu_memory{&memory};
    Cache pipeline_cache;
    explicit Rig(std::size_t descriptors, std::size_t used,
                 bool switch_to_empty = false) {
        assert(used < Queue::frame_payload_size);
        pipeline = descriptors == 0 ? &empty :
                   descriptors == 1 ? &one : &many;
        pipeline_cache.selected = pipeline;
        guest_descriptor_queue.payload_cursor += used;
        if (switch_to_empty)
            scheduler.after_wait = [this] { pipeline_cache.selected = &empty; };
    }
    void GraphLoop() { GRAPH_LOOP }
    void GraphReuse() { GRAPH_REUSE }
    void GraphCapacity() { GRAPH_CAPACITY }
    void ComputeLoop() { COMPUTE_LOOP }
    void ComputeReuse() { COMPUTE_REUSE }
    void ComputeCapacity() { COMPUTE_CAPACITY }
};
using Method = void (Rig::*)();
void check(Method method) {
    // Even a nearly exhausted guest descriptor queue must not stall on
    // shaders that produce exactly zero descriptors.
    Rig empty(0, 4095);
    (empty.*method)();
    assert(empty.scheduler.waits == 0);
    assert(empty.guest_descriptor_queue.payload_cursor ==
           empty.guest_descriptor_queue.payload_start + 4095);

    // Exact parity with upstream Acquire: one entry at the last slot needs
    // the worker drain, including after a previous unrelated worker wait
    // has published a new small-descriptor shader.
    Rig one(1, 4095, true);
    (one.*method)();
    assert(one.scheduler.waits == 1);
    assert(one.pipeline == &one.empty);
    assert(one.guest_descriptor_queue.payload_cursor ==
           one.guest_descriptor_queue.payload_start);

    // When enough room remains, no speculative worker drain should occur.
    Rig room(1, 4000);
    (room.*method)();
    assert(room.scheduler.waits == 0);
    assert(room.guest_descriptor_queue.payload_cursor ==
           room.guest_descriptor_queue.payload_start + 4000);

    Rig many(2048, 3500, true);
    (many.*method)();
    assert(many.scheduler.waits == 1);
    assert(many.pipeline == &many.empty);
}
int main() {
    // The old helper could not pre-drain <1024 descriptors even with one
    // free entry remaining. The new helper matches Acquire's exact bound.
    Queue q;
    q.payload_cursor += 4095;
    int prior_waits = 0;
    assert(!q.OldLargePreflightDraw([&] { ++prior_waits; }, 1));
    assert(prior_waits == 0);
    int exact_waits = 0;
    assert(q.PreflightExactGuestDraw([&] { ++exact_waits; }, 1));
    assert(exact_waits == 1 && q.payload_cursor == q.payload_start);

    // The first/pre-lock preflight now uses the known exact count, not
    // the conservative 1024-entry default, avoiding a premature drain.
    Queue room;
    room.payload_cursor += 4000;
    int early_waits = 0;
    assert(!room.PreflightGuestDraw([&] { ++early_waits; }, 1));
    assert(early_waits == 0);
    assert(room.PreflightGuestDraw([&] { ++early_waits; }));
    assert(early_waits == 1);
    Queue edge;
    edge.payload_cursor += 4095;
    int edge_waits = 0;
    assert(edge.PreflightGuestDraw([&] { ++edge_waits; }, 1));
    assert(edge_waits == 1 && edge.payload_cursor == edge.payload_start);
    for (Method method : {
        &Rig::GraphLoop, &Rig::GraphReuse, &Rig::GraphCapacity,
        &Rig::ComputeLoop, &Rig::ComputeReuse, &Rig::ComputeCapacity
    }) check(method);
    std::puts("SIX_NATIVE_DESCRIPTOR_PREFLIGHT_EXACT_PARITY_PASS");
}
"""
for tag, block in [
    ("OLD_HELPER", prior), ("HELPER", helper),
    ("GRAPH_LOOP", gl), ("GRAPH_REUSE", gb[0]), ("GRAPH_CAPACITY", gb[1]),
    ("COMPUTE_LOOP", cl), ("COMPUTE_REUSE", cb[0]),
    ("COMPUTE_CAPACITY", cb[1])
]:
    # Replace the longer OLD_HELPER placeholder first; replacing HELPER
    # before it would corrupt the old-method declaration.
    assert cpp.count(tag) == 1, tag
    cpp = cpp.replace(tag, block)
assert cpp.count("__INITIAL_METHOD__") == 1
cpp = cpp.replace("__INITIAL_METHOD__", initial)
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-exact-preflight-") as d:
    filename = Path(d) / "preflight.cpp"
    filename.write_text(cpp)
    for opt in ("-O0", "-O2"):
        exe = Path(d) / ("preflight" + opt)
        built = subprocess.run(
            [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
             "-fsanitize=undefined", "-fno-sanitize-recover=all",
             str(filename), "-o", str(exe)],
            capture_output=True, text=True, timeout=60)
        assert built.returncode == 0, (opt, built.stderr[-5000:])
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        assert run.returncode == 0, (opt, run.stdout, run.stderr[-5000:])
        assert "SIX_NATIVE_DESCRIPTOR_PREFLIGHT_EXACT_PARITY_PASS" in run.stdout
        print("DESCRIPTOR_PREFLIGHT_EXACT_SOURCE_PASS", opt)
