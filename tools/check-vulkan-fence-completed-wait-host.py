#!/usr/bin/env python3
"""Compile the real Vulkan Queue -> IsSignaled -> Wait fence path, host only.

Both pinned and maintained implementations use the real extracted C++ methods,
including FenceManager delegation. No native semaphore timing or PS5 FPS claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = (ROOT / "vendor/encore-active/eden-vulkan/vk_fence_manager_cost.cpp").read_text()
PINNED = (ROOT / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_fence_manager.cpp").read_text()
GENERATOR = (ROOT / "tools/prepare-vulkan-port.py").read_text()
FAST = (ROOT / ".github/workflows/encore-core-fast-gate.yml").read_text()
FULL = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()

assert "python3 -B tools/check-vulkan-fence-completed-wait-host.py" in FAST
assert "python3 -B tools/check-vulkan-fence-completed-wait-host.py" in FULL
assert "'vk_fence_manager': [" in GENERATOR
assert "scheduler.IsFree(wait_tick)" in GENERATOR

SIGNATURES = (
    "void InnerFence::Queue()",
    "bool InnerFence::IsSignaled() const",
    "void InnerFence::Wait()",
    "void FenceManager::QueueFence(Fence& fence)",
    "bool FenceManager::IsFenceSignaled(Fence& fence) const",
    "void FenceManager::WaitFence(Fence& fence)",
)


def extract_method(source: str, signature: str) -> str:
    marker = signature + " {"
    assert source.count(marker) == 1, signature
    start = source.index(marker)
    opening = start + len(signature) + 1
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError("unbalanced C++ method: " + signature)


original = [extract_method(PINNED, symbol) for symbol in SIGNATURES]
maintained = [extract_method(ACTIVE, symbol) for symbol in SIGNATURES]
assert original[:2] == maintained[:2] and original[3:] == maintained[3:]
assert "scheduler.IsFree(wait_tick)" in maintained[2]
assert "scheduler.IsFree(wait_tick)" not in original[2]
assert original[2].count("scheduler.Wait(wait_tick);") == 1
assert maintained[2].count("scheduler.Wait(wait_tick);") == 1
# The real instrumentation timer has a destructor; the host double simply
# counts construction, so tell -Wunused-variable that this is intentional.
maintained[2] = maintained[2].replace(
    "auto timer = Eden::Performance::VulkanTimer(6)",
    "[[maybe_unused]] auto timer = Eden::Performance::VulkanTimer(6)",
)

cpp = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>

struct Scheduler {
    std::uint64_t current{9};
    std::uint64_t completed{5};
    mutable unsigned queries{};
    unsigned samples{}, flushes{}, waits{};
    std::uint64_t CurrentTick() { ++samples; return current; }
    void Flush() { ++flushes; }
    bool IsFree(std::uint64_t tick) const {
        ++queries;
        return tick <= completed;
    }
    void Wait(std::uint64_t tick) {
        ++waits;
        if (completed < tick) completed = tick;
    }
};

namespace Eden::Performance {
struct VulkanTimer {
    static inline unsigned starts{};
    explicit VulkanTimer(unsigned) { ++starts; }
};
}

struct InnerFence {
    Scheduler& scheduler;
    bool is_stubbed{};
    std::uint64_t wait_tick{};
    InnerFence(Scheduler& s, bool stubbed) : scheduler(s), is_stubbed(stubbed) {}
    void Queue();
    bool IsSignaled() const;
    void Wait();
};
using Fence = std::shared_ptr<InnerFence>;
struct FenceManager {
    void QueueFence(Fence&);
    bool IsFenceSignaled(Fence&) const;
    void WaitFence(Fence&);
};

INJECT

int main() {
    Scheduler scheduler;
    FenceManager manager;

    Fence stubbed = std::make_shared<InnerFence>(scheduler, true);
    manager.QueueFence(stubbed);
    assert(manager.IsFenceSignaled(stubbed));
    manager.WaitFence(stubbed);
    assert(scheduler.samples == 0 && scheduler.flushes == 0);
    assert(scheduler.waits == 0 && scheduler.queries == 0);

    Fence pending = std::make_shared<InnerFence>(scheduler, false);
    manager.QueueFence(pending);
    assert(pending->wait_tick == 9);
    assert(scheduler.samples == 1 && scheduler.flushes == 1);
    // Changing the producer tick cannot change an already queued fence.
    scheduler.current = 17;
    assert(!manager.IsFenceSignaled(pending));
    manager.WaitFence(pending);
    assert(scheduler.completed == 9 && scheduler.waits == 1);
    assert(manager.IsFenceSignaled(pending));
    manager.WaitFence(pending);

    // A newly queued fence can refer to a tick already completed.
    scheduler.current = 3;
    Fence completed = std::make_shared<InnerFence>(scheduler, false);
    manager.QueueFence(completed);
    assert(completed->wait_tick == 3);
    assert(manager.IsFenceSignaled(completed));
    manager.WaitFence(completed);

    assert(scheduler.samples == 2 && scheduler.flushes == 2);
    assert(scheduler.waits == EXPECTED_WAITS);
    assert(scheduler.queries == EXPECTED_QUERIES);
    assert(Eden::Performance::VulkanTimer::starts == EXPECTED_TIMERS);
    std::puts("ENCORE_VULKAN_FENCE_FULL_HANDOFF_HOST_PASS");
}
"""

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "host C++20 compiler unavailable"
with tempfile.TemporaryDirectory(prefix="encore-vulkan-fence-handoff-") as tmp:
    root = Path(tmp)
    for name, methods, waits, queries, timers in (
        ("pinned", original, 3, 3, 0),
        ("native", maintained, 1, 6, 1),
    ):
        src = root / (name + ".cpp")
        exe = root / name
        code = cpp.replace("INJECT", "\n\n".join(methods))
        code = code.replace("EXPECTED_WAITS", str(waits))
        code = code.replace("EXPECTED_QUERIES", str(queries))
        code = code.replace("EXPECTED_TIMERS", str(timers))
        src.write_text(code)
        subprocess.run(
            [compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
             "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
             str(src), "-o", str(exe)],
            check=True, timeout=90,
        )
        subprocess.run([str(exe)], check=True, timeout=30)

print("VULKAN_FENCE_HANDOFF_HOST_PASS; native GPU waits and PS5 FPS unmeasured")
