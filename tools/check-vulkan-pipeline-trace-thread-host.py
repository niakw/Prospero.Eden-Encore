#!/usr/bin/env python3
"""C++20 ASan/UBSan/TSan check of actual debug-only pipeline trace registry.

The exact generator strings are AST-extracted to verify both PS5 graphics and
compute pipeline-cache sites use the shared epoch/mutex helper and do not
retain unprotected function-static unordered_sets. This is NOT a GPU SDK run.
"""
import ast
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
generator = (root / "tools/prepare-vulkan-port.py").read_text()
tree = ast.parse(generator)
shader_costs = None
for node in tree.body:
    if (isinstance(node, ast.Assign) and any(
            isinstance(x, ast.Name) and x.id == "shader_costs"
            for x in node.targets)):
        shader_costs = ast.literal_eval(node.value)
        break
assert shader_costs
generated = "\n".join(rhs for lhs, rhs in shader_costs)
assert "PipelineTrace::graphics_first_use.Record(" in generated
assert "PipelineTrace::compute_first_use.Record(" in generated
assert generated.count("gpu_time_session.load(std::memory_order_acquire)") == 2
assert "traced.insert" not in generated and "traced.size()" not in generated
assert '#include "pipeline_trace_registry.h"' in generated
header = (root / "headless/pipeline_trace_registry.h").read_text()
assert "std::lock_guard lock(mutex_)" in header
assert "seen_.clear()" in header
assert "if (seen_.size() >= kMaxPipelinesPerTitle)" in header
assert "return inserted ? seen_.size() : 0;" in header

compiler = next((c for c in ("clang++-18", "clang++", "g++")
                 if shutil.which(c)), None)
if compiler is None:
    raise SystemExit("Missing C++20 compiler; no valid pipeline trace host proof")

cpp = r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <thread>
#include <vector>
#include "pipeline_trace_registry.h"
using Eden::PipelineTrace::FirstUseRegistry;

int main() {
    std::vector<int> addresses(256);
    FirstUseRegistry registry;
    std::atomic<unsigned> first_use_count{0};
    std::vector<std::thread> workers;
    constexpr unsigned kWorkers = 16;
    for (unsigned worker = 0; worker < kWorkers; ++worker) {
        workers.emplace_back([&, worker] {
            for (unsigned trial = 0; trial < 256; ++trial) {
                const auto index = (worker * 13 + trial) % addresses.size();
                const auto ordinal = registry.Record(1, &addresses[index]);
                if (ordinal) {
                    assert(ordinal <= addresses.size());
                    first_use_count.fetch_add(1, std::memory_order_relaxed);
                }
            }
        });
    }
    for (auto& worker : workers) worker.join();
    assert(first_use_count.load() == addresses.size());
    assert(registry.CountForTest() == addresses.size());
    assert(registry.Record(1, &addresses[5]) == 0);
    assert(registry.Record(2, &addresses[5]) == 1); // reused pointer, new game
    assert(registry.CountForTest() == 1);
    assert(registry.Record(2, nullptr) == 0);

    // Bound long-lived debug allocation without mutating normal Vulkan paths.
    std::vector<int> many(FirstUseRegistry::kMaxPipelinesPerTitle + 1);
    for (std::size_t i = 0; i < many.size(); ++i) {
        auto ordinal = registry.Record(3, &many[i]);
        if (i < FirstUseRegistry::kMaxPipelinesPerTitle)
            assert(ordinal == i + 1);
        else
            assert(ordinal == 0);
    }
    assert(registry.CountForTest() == FirstUseRegistry::kMaxPipelinesPerTitle);
    assert(registry.Record(4, &many.back()) == 1);
    assert(registry.CountForTest() == 1);

    // No accidental sharing of compute/graphics debug IDs.
    assert(Eden::PipelineTrace::graphics_first_use.Record(5, &many[0]) == 1);
    assert(Eden::PipelineTrace::compute_first_use.Record(5, &many[0]) == 1);
    assert(Eden::PipelineTrace::graphics_first_use.Record(5, &many[0]) == 0);
    assert(Eden::PipelineTrace::compute_first_use.Record(6, &many[0]) == 1);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-vk-trace-") as folder:
    file = Path(folder) / "trace.cpp"
    file.write_text(cpp)
    flags = [compiler, "-std=c++20", "-O1", "-g", "-pthread",
             "-Wall", "-Wextra", "-Werror",
             "-fno-sanitize-recover=all", "-I", str(root / "headless")]
    binary = Path(folder) / "trace-asan"
    subprocess.run([*flags, "-fsanitize=address,undefined",
                    str(file), "-o", str(binary)], check=True, timeout=90)
    subprocess.run([str(binary)], check=True, timeout=180)
    if platform.system() == "Linux" and platform.machine() in ("x86_64", "aarch64"):
        tsan = Path(folder) / "trace-tsan"
        subprocess.run([*flags, "-fsanitize=thread",
                        str(file), "-o", str(tsan)], check=True, timeout=90)
        subprocess.run([str(tsan)], check=True, timeout=180)
print("PASS thread-safe Vulkan pipeline first-use trace: 16 workers, epoch reset, 65536 max, ASan/UBSan/TSan")
print("No native PS5 compiler/renderer tested")
