#!/usr/bin/env python3
"""Compile selected producer detach method; verify dequeuer generation wake after free."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
active = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
pinned = (ROOT / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
core = (ROOT / "vendor/encore-active/eden-backports/src/core/hle/service/nvnflinger/buffer_queue_core.cpp").read_text()
cmake = (ROOT / "headless/CMakeLists.txt").read_text()
oracle = (ROOT / "tools/check-vendor-consolidation-debt.py").read_text()
assert 'list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_DEQUEUE}")' in cmake
assert 'dequeue_expected = dequeue_expected.replace(detach_before, detach_after)' in oracle
assert "dequeue_epoch.fetch_add(1, std::memory_order_relaxed)" in core
sig = "Status BufferQueueProducer::DetachNextBuffer("
def method(src):
    assert src.count(sig) == 1
    start = src.index(sig)
    end = src.index("\nStatus BufferQueueProducer::AttachBuffer(", start)
    return src[start:end].rstrip()
selected = method(active)
assert 'core->FreeBufferLocked(found);\n    // DetachBuffer' in selected
assert selected.count("core->SignalDequeueCondition();") == 1
assert selected.index("core->FreeBufferLocked(found);") < selected.index("core->SignalDequeueCondition();")
assert "core->SignalDequeueCondition();" not in method(pinned)

fixture = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <memory>
#include <mutex>
using s32 = int;
using u32 = std::uint32_t;
enum class Status { NoError, BadValue, NoInit, NoMemory };
enum class BufferState { Free, Dequeued, Acquired };
struct Fence { int sequence{}; };
struct GraphicBuffer { int payload{}; };
struct BufferQueueDefs { static constexpr s32 NUM_BUFFER_SLOTS = 4; };
#define LOG_ERROR(...) (void)0
#define LOG_DEBUG(...) (void)0
struct BufferSlot {
    BufferState buffer_state{BufferState::Free};
    std::shared_ptr<GraphicBuffer> graphic_buffer{};
    u32 frame_number{};
    Fence fence{};
};
struct BufferQueueCore {
    static constexpr s32 INVALID_BUFFER_SLOT = -1;
    std::mutex mutex{};
    std::array<BufferSlot, BufferQueueDefs::NUM_BUFFER_SLOTS> slots{};
    bool is_abandoned{};
    int notifications{};
    void WaitWhileAllocatingLocked() const {}
    void FreeBufferLocked(s32 index) {
        auto& slot = slots[index];
        slot.graphic_buffer.reset();
        slot.buffer_state = BufferState::Free;
        slot.frame_number = 0xffffffffu;
    }
    void SignalDequeueCondition() {
        assert(slots[0].graphic_buffer == nullptr ||
               slots[1].graphic_buffer == nullptr ||
               slots[2].graphic_buffer == nullptr ||
               slots[3].graphic_buffer == nullptr);
        ++notifications;
    }
};
struct BufferQueueProducer {
    BufferQueueCore* core{};
    std::array<BufferSlot, BufferQueueDefs::NUM_BUFFER_SLOTS>& slots;
    explicit BufferQueueProducer(BufferQueueCore& c) : core(&c), slots(c.slots) {}
    Status DetachNextBuffer(std::shared_ptr<GraphicBuffer>* out_buffer, Fence* out_fence);
};
""" + "\n" + selected + r"""
int main() {
    BufferQueueCore core{};
    BufferQueueProducer p(core);
    std::shared_ptr<GraphicBuffer> output;
    Fence fence{};
    assert(p.DetachNextBuffer(nullptr, &fence) == Status::BadValue);
    assert(p.DetachNextBuffer(&output, nullptr) == Status::BadValue);
    assert(core.notifications == 0);
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoMemory);
    assert(core.notifications == 0);
    // Oldest free graphic buffer is detached first. The active slot is
    // cleared BEFORE a single shared dequeue-generation wake is published.
    core.slots[0].graphic_buffer = std::make_shared<GraphicBuffer>(GraphicBuffer{123});
    core.slots[0].frame_number = 77;
    core.slots[0].fence = Fence{2};
    core.slots[1].graphic_buffer = std::make_shared<GraphicBuffer>(GraphicBuffer{456});
    core.slots[1].frame_number = 7;
    core.slots[1].fence = Fence{9};
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoError);
    assert(output && output->payload == 456 && fence.sequence == 9);
    assert(core.slots[1].graphic_buffer == nullptr);
    assert(core.notifications == 1);
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoError);
    assert(output && output->payload == 123 && fence.sequence == 2);
    assert(core.notifications == 2);
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoMemory);
    assert(core.notifications == 2);
    core.is_abandoned = true;
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoInit);
    assert(core.notifications == 2);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "host C++ compiler required"
with tempfile.TemporaryDirectory(prefix="encore-nvn-detach-") as tmp:
    source = Path(tmp) / "detach.cpp"
    source.write_text(fixture)
    for opt in ("-O0", "-O2"):
        binary = Path(tmp) / ("detach" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(source), "-o", str(binary)], check=True, timeout=40)
        subprocess.run([str(binary)], check=True, timeout=15)
        print("NATIVE_NVN_DETACH_WAKE_PASS", opt)
