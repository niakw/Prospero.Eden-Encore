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
assert 'target_compile_definitions(core PRIVATE EDEN_NVNF_DEQUEUE_PROFILE=1)' in cmake
assert 'dequeue_expected = dequeue_expected.replace(detach_before, detach_after)' in oracle
assert "dequeue_epoch.fetch_add(1, std::memory_order_relaxed)" in core
core_methods_start = core.index("void BufferQueueCore::SignalDequeueCondition() {")
core_methods_end = core.index("s32 BufferQueueCore::GetMinUndequeuedBufferCountLocked(", core_methods_start)
core_methods = core[core_methods_start:core_methods_end].rstrip()
assert core_methods.count("dequeue_condition.notify_all();") == 1
assert "dequeue_condition.wait(lk," in core_methods
sig = "Status BufferQueueProducer::DetachNextBuffer("
def method(src):
    assert src.count(sig) == 1
    start = src.index(sig)
    end = src.index("\nStatus BufferQueueProducer::AttachBuffer(", start)
    return src[start:end].rstrip()
selected = method(active)
single_begin = "Status BufferQueueProducer::DetachBuffer("
single_end = "Status BufferQueueProducer::DetachNextBuffer("
assert active.count(single_begin) == 1 and active.count(single_end) == 1
selected_single = active[active.index(single_begin):active.index(single_end)].rstrip()
count_begin = "Status BufferQueueProducer::SetBufferCount("
count_end = "Status BufferQueueProducer::WaitForFreeSlotThenRelock("
assert active.count(count_begin) == 1 and active.count(count_end) == 1
selected_count = active[active.index(count_begin):active.index(count_end)].rstrip()
assert selected_count.count("buffer_wait_event->Signal(service_context.kernel);") == 2
# F05: the guest event enters the kernel scheduler. Every native producer
# wake must occur after its queue mutex has been released. Keep host
# SignalDequeueCondition() under the lock for the dequeue epoch contract.
assert "std::unique_lock lock{core->mutex};" in selected_count
assert "lock.unlock();\n            buffer_wait_event->Signal(service_context.kernel);" in selected_count
assert "    }\n    buffer_wait_event->Signal(service_context.kernel);\n" in selected_count
assert "std::unique_lock lock{core->mutex};" in selected_single
assert "lock.unlock();\n    buffer_wait_event->Signal(service_context.kernel);" in selected_single
assert "std::unique_lock lock{core->mutex};" in selected
assert "lock.unlock();\n    buffer_wait_event->Signal(service_context.kernel);" in selected

def check_producer_unlocked_method(begin, end, before_signal):
    body=active[active.index(begin):active.index(end,active.index(begin))]
    assert body.count("buffer_wait_event->Signal(service_context.kernel);") == 1
    assert before_signal in body, ("guest event still under core mutex", begin)
    return body

cancel=check_producer_unlocked_method(
    "void BufferQueueProducer::CancelBuffer(",
    "Status BufferQueueProducer::Query(",
    "core->SignalDequeueCondition();\n    lock.unlock();\n"
)
assert "std::unique_lock lock{core->mutex};" in cancel
disconnect=check_producer_unlocked_method(
    "Status BufferQueueProducer::Disconnect(",
    "Status BufferQueueProducer::SetPreallocatedBuffer(",
    "    }\n\n    if (released_queue) {\n"
)
assert disconnect.index("    if (released_queue) {") < disconnect.index(
    "buffer_wait_event->Signal(service_context.kernel);")
preallocate=check_producer_unlocked_method(
    "Status BufferQueueProducer::SetPreallocatedBuffer(",
    "Kernel::KReadableEvent* BufferQueueProducer::GetNativeHandle(",
    "core->SignalDequeueCondition();\n    lock.unlock();\n"
)
assert "std::unique_lock lock{core->mutex};" in preallocate
queued=check_producer_unlocked_method(
    "Status BufferQueueProducer::QueueBuffer(",
    "void BufferQueueProducer::CancelBuffer(",
    "        output->Inflate("
)
assert queued.index("        output->Inflate(") < queued.index(
    "buffer_wait_event->Signal(service_context.kernel);")
assert "    }\n\n    if (recycled_queued_slot) {" in queued
assert "core->override_max_buffer_count = 0;" in selected_count
assert selected_count.index("core->override_max_buffer_count = 0;") < selected_count.index(
    "buffer_wait_event->Signal(service_context.kernel);")

assert selected_single.count("core->SignalDequeueCondition();") == 1
assert selected_single.count("buffer_wait_event->Signal(service_context.kernel);") == 1
assert selected_single.index("core->FreeBufferLocked(slot);") < selected_single.index(
    "buffer_wait_event->Signal(service_context.kernel);")
assert "buffer_wait_event->Signal(service_context.kernel);" not in pinned[
    pinned.index(single_begin):pinned.index(single_end)]
assert 'core->FreeBufferLocked(found);\n    // DetachBuffer' in selected
assert selected.count("core->SignalDequeueCondition();") == 1
assert selected.count("buffer_wait_event->Signal(service_context.kernel);") == 1
assert selected.index("core->FreeBufferLocked(found);") < selected.index("core->SignalDequeueCondition();")
assert "core->SignalDequeueCondition();" not in method(pinned)
assert "buffer_wait_event->Signal(service_context.kernel);" not in method(pinned)

fixture = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <memory>
#include <mutex>
#include <thread>
using s32 = int;
using u32 = std::uint32_t;
enum class Status { NoError, BadValue, NoInit, NoMemory };
enum class BufferState { Free, Dequeued, Acquired };
struct Fence { int sequence{}; };
struct GraphicBuffer { int payload{}; };
struct BufferQueueDefs { static constexpr s32 NUM_BUFFER_SLOTS = 4; };
#define LOG_ERROR(...) (void)0
#define LOG_DEBUG(...) (void)0
struct IConsumerListener {
    int calls{};
    void OnBuffersReleased() { ++calls; }
};
struct BufferSlot {
    BufferState buffer_state{BufferState::Free};
    std::shared_ptr<GraphicBuffer> graphic_buffer{};
    u32 frame_number{};
    Fence fence{};
    bool request_buffer_called{};
    bool is_preallocated{};
};
struct BufferQueueCore {
    static constexpr s32 INVALID_BUFFER_SLOT = -1;
    std::mutex mutex{};
    std::array<BufferSlot, BufferQueueDefs::NUM_BUFFER_SLOTS> slots{};
    bool is_abandoned{};
    s32 override_max_buffer_count{};
    std::shared_ptr<IConsumerListener> consumer_listener{};
    std::condition_variable dequeue_condition{};
    std::atomic<std::uint64_t> dequeue_epoch{};
    void WaitWhileAllocatingLocked() const {}
    s32 GetMinMaxBufferCountLocked(bool) const { return 1; }
    s32 GetPreallocatedBufferCountLocked() const { return 0; }
    void FreeAllBuffersLocked() {
        for (s32 i = 0; i < BufferQueueDefs::NUM_BUFFER_SLOTS; ++i) FreeBufferLocked(i);
    }
    void FreeBufferLocked(s32 index) {
        auto& slot = slots[index];
        slot.graphic_buffer.reset();
        slot.buffer_state = BufferState::Free;
        slot.frame_number = 0xffffffffu;
    }
    void SignalDequeueCondition();
    bool WaitForDequeueCondition(std::unique_lock<std::mutex>& lk);
};
struct MockKernel {};
struct MockEvent {
    std::atomic<int> signals{};
    void Signal(MockKernel&) {signals.fetch_add(1);}
};
struct MockServiceContext {MockKernel kernel{};};
struct BufferQueueProducer {
    MockServiceContext service_context{};
    MockEvent event{};
    MockEvent* buffer_wait_event{&event};
    BufferQueueCore* core{};
    std::array<BufferSlot, BufferQueueDefs::NUM_BUFFER_SLOTS>& slots;
    explicit BufferQueueProducer(BufferQueueCore& c) : core(&c), slots(c.slots) {}
    Status DetachNextBuffer(std::shared_ptr<GraphicBuffer>* out_buffer, Fence* out_fence);
    Status DetachBuffer(s32 slot);
    Status SetBufferCount(s32 count);
};
""" + "\n" + core_methods + "\n" + selected_single + "\n" + selected_count + "\n" + selected + r"""
int main() {
    BufferQueueCore core{};
    BufferQueueProducer p(core);
    std::shared_ptr<GraphicBuffer> output;
    Fence fence{};
    assert(p.DetachNextBuffer(nullptr, &fence) == Status::BadValue);
    assert(p.DetachNextBuffer(&output, nullptr) == Status::BadValue);
    assert(core.dequeue_epoch.load() == 0);
    assert(p.event.signals.load() == 0);
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoMemory);
    assert(core.dequeue_epoch.load() == 0);
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
    assert(core.dequeue_epoch.load() == 1);
    assert(p.event.signals.load() == 1);
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoError);
    assert(output && output->payload == 123 && fence.sequence == 2);
    assert(core.dequeue_epoch.load() == 2);
    assert(p.event.signals.load() == 2);
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoMemory);
    assert(core.dequeue_epoch.load() == 2);
    assert(p.event.signals.load() == 2);
    core.is_abandoned = true;
    assert(p.DetachNextBuffer(&output, &fence) == Status::NoInit);
    assert(core.dequeue_epoch.load() == 2);
    assert(p.event.signals.load() == 2);

    // A second producer path detaches an owned dequeued slot, notifies the
    // host broadcast and the native guest event exactly once on success.
    BufferQueueCore single{};
    BufferQueueProducer owned(single);
    assert(owned.DetachBuffer(-1) == Status::BadValue);
    assert(owned.DetachBuffer(0) == Status::BadValue);
    single.slots[0].buffer_state = BufferState::Dequeued;
    single.slots[0].graphic_buffer = std::make_shared<GraphicBuffer>(GraphicBuffer{123});
    assert(owned.DetachBuffer(0) == Status::BadValue);
    single.slots[0].request_buffer_called = true;
    assert(owned.DetachBuffer(0) == Status::NoError);
    assert(single.slots[0].buffer_state == BufferState::Free);
    assert(!single.slots[0].graphic_buffer);
    assert(single.dequeue_epoch.load() == 1);
    assert(owned.event.signals.load() == 1);
    assert(owned.DetachBuffer(0) == Status::BadValue);
    assert(owned.event.signals.load() == 1);

    // The zero-count reset formerly signalled only host waiters, not the
    // Binder native event. Both zero and positive changes now wake the guest.
    BufferQueueCore sized{};
    BufferQueueProducer count_producer(sized);
    sized.consumer_listener = std::make_shared<IConsumerListener>();
    assert(count_producer.SetBufferCount(BufferQueueDefs::NUM_BUFFER_SLOTS+1) == Status::BadValue);
    assert(count_producer.event.signals.load() == 0);
    sized.slots[0].buffer_state = BufferState::Dequeued;
    assert(count_producer.SetBufferCount(0) == Status::BadValue);
    assert(count_producer.event.signals.load() == 0);
    sized.slots[0].buffer_state = BufferState::Free;
    assert(count_producer.SetBufferCount(0) == Status::NoError);
    assert(sized.override_max_buffer_count == 0);
    assert(count_producer.event.signals.load() == 1);
    assert(sized.dequeue_epoch.load() == 1);
    assert(sized.consumer_listener->calls == 0);
    assert(count_producer.SetBufferCount(2) == Status::NoError);
    assert(sized.override_max_buffer_count == 2);
    assert(count_producer.event.signals.load() == 2);
    assert(sized.dequeue_epoch.load() == 2);
    assert(sized.consumer_listener->calls == 1);

    // Deterministically place TWO producers inside the actual core condition
    // wait: each must release the mutex for the next one to enter.
    // The selected DetachNextBuffer must broadcast its generation update.
    for (int round = 0; round < 50; ++round) {
        BufferQueueCore blocked{};
        BufferQueueProducer detacher(blocked);
        blocked.slots[0].graphic_buffer = std::make_shared<GraphicBuffer>(GraphicBuffer{round});
        blocked.slots[0].frame_number = 1;
        std::atomic<int> entered{};
        std::atomic<int> woke{};
        auto waiter = [&] {
            std::unique_lock lock(blocked.mutex);
            entered.fetch_add(1);
            const bool awakened = blocked.WaitForDequeueCondition(lock);
            if (awakened) woke.fetch_add(1);
        };
        std::thread first(waiter), second(waiter);
        while (entered.load() != 2) std::this_thread::yield();
        // Acquiring core mutex guarantees both waiters have entered wait().
        { std::unique_lock lock(blocked.mutex); }
        std::shared_ptr<GraphicBuffer> detached{};
        Fence detached_fence{};
        assert(detacher.DetachNextBuffer(&detached, &detached_fence) == Status::NoError);
        assert(detached && detached->payload == round);
        using namespace std::chrono_literals;
        const auto deadline = std::chrono::steady_clock::now() + 2s;
        while (woke.load() != 2 && std::chrono::steady_clock::now() < deadline)
            std::this_thread::yield();
        assert(woke.load() == 2);
        assert(blocked.dequeue_epoch.load() == 1);
        assert(detacher.event.signals.load() == 1);
        first.join();
        second.join();
    }
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
                        "-Werror", "-pthread", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(source), "-o", str(binary)], check=True, timeout=40)
        subprocess.run([str(binary)], check=True, timeout=15)
        print("NATIVE_NVN_DETACH_BROADCAST_PASS", opt)
