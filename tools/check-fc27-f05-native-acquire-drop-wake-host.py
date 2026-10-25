#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05: execute native AcquireBuffer dropping frames -> guest Binder release event.

Select the maintained consumer's actual method and the shipping producer
listener. Mocks shared buffer storage and the guest kernel event, not FC27.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp").read_text()
PINNED = (ROOT / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp").read_text()
PRODUCER = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
CMAKE = (ROOT / "headless/CMakeLists.txt").read_text()
assert 'list(APPEND core_sources "\x24{EDEN_MAINTAINED_NVNF_CONSUMER}")' in CMAKE

def method(text, sig):
    assert text.count(sig) == 1, sig
    begin = text.index(sig)
    brace = text.index("{", begin)
    depth = 0
    for end in range(brace, len(text)):
        if text[end] == "{": depth += 1
        elif text[end] == "}":
            depth -= 1
            if depth == 0: return text[begin:end + 1]
    raise AssertionError(sig)

signature = "Status BufferQueueConsumer::AcquireBuffer("
active = method(CONSUMER, signature)
pinned = method(PINNED, signature)
assert "dropped_queued_frames = true;" in active
assert "dropped_queued_frames = true;" not in pinned
assert active.count("listener->OnBufferReleased();") == 2
assert active.count("lock.unlock();") == 2
assert "std::unique_lock lock{core->mutex};" in active
assert active.count("core->SignalDequeueCondition();") == 2
listener_begin = "class ProducerReleaseWake final : public IProducerListener {"
assert PRODUCER.count(listener_begin) == 1
start = PRODUCER.index(listener_begin)
listener = PRODUCER[start:PRODUCER.index("\n};", start) + 3]
assert "event->Signal(kernel);" in listener

cpp = r"""
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <vector>
#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
using s32 = std::int32_t;
using s64 = std::int64_t;
namespace Kernel {
struct KernelCore {};
struct KEvent {
    std::atomic<int> signals{};
    void Signal(KernelCore&) { signals.fetch_add(1); }
};
}
namespace Service::android {
enum class Status { NoError, InvalidOperation, NoBufferAvailable, PresentLater };
enum class BufferState {Free, Queued, Acquired};
struct GraphicBuffer { int id{}; };
struct BufferItem {
    s32 slot{};
    std::shared_ptr<GraphicBuffer> graphic_buffer{};
    bool is_auto_timestamp{};
    s64 timestamp{};
    bool acquire_called{};
};
struct BufferSlot {
    BufferState buffer_state{BufferState::Free};
    bool acquire_called{};
    bool needs_cleanup_on_release{};
    std::shared_ptr<GraphicBuffer> graphic_buffer{};
};
struct IProducerListener {
    virtual ~IProducerListener() = default;
    virtual void OnBufferReleased() = 0;
};
struct BufferQueueCore {
    std::mutex mutex{};
    std::array<BufferSlot, 4> slots{};
    std::vector<BufferItem> queue{};
    int max_acquired_buffer_count{};
    std::shared_ptr<IProducerListener> connected_producer_listener{};
    std::atomic<int> broadcasts{};
    bool StillTracking(const BufferItem& item) const {
        return slots[item.slot].graphic_buffer == item.graphic_buffer
            && item.graphic_buffer != nullptr;
    }
    void SignalDequeueCondition() { broadcasts.fetch_add(1); }
};
struct BufferQueueConsumer {
    std::shared_ptr<BufferQueueCore> core;
    std::array<BufferSlot,4>& slots;
    explicit BufferQueueConsumer(std::shared_ptr<BufferQueueCore> c)
        : core(std::move(c)), slots(core->slots) {}
    Status AcquireBuffer(BufferItem* out_buffer, std::chrono::nanoseconds expected_present);
};
__WAKE__
__ACQUIRE__
struct Delegate final : IProducerListener {
    BufferQueueCore& core;
    int callbacks{};
    bool unlocked{true};
    explicit Delegate(BufferQueueCore& c):core(c){}
    void OnBufferReleased() override {
        if (core.mutex.try_lock()) core.mutex.unlock();
        else unlocked = false;
        ++callbacks;
    }
};
}
int main() {
    using namespace Service::android;
    Kernel::KernelCore kernel;
    Kernel::KEvent event;
    auto core=std::make_shared<BufferQueueCore>();
    auto wake=std::make_shared<ProducerReleaseWake>(&event,kernel);
    auto delegate=std::make_shared<Delegate>(*core);
    wake->SetDelegate(delegate);
    core->connected_producer_listener=wake;
    BufferQueueConsumer c(core);
    // A deadline-aware acquire skips two queued frames and retains the last.
    for (int frame=0; frame<260; ++frame) {
        core->queue.clear();
        for (int slot=0;slot<3;++slot) {
            auto b=std::make_shared<GraphicBuffer>(GraphicBuffer{frame*3+slot});
            core->slots[slot].graphic_buffer=b;
            core->slots[slot].buffer_state=BufferState::Queued;
            core->slots[slot].acquire_called=false;
            core->queue.push_back(BufferItem{slot,b,false,1'500'000'000LL+slot*200'000'000LL,false});
        }
        BufferItem out{};
        assert(c.AcquireBuffer(&out,std::chrono::nanoseconds{2'000'000'000})==Status::NoError);
        assert(out.slot==2 && out.graphic_buffer->id==frame*3+2);
        assert(core->queue.empty());
        assert(core->slots[0].buffer_state==BufferState::Free);
        assert(core->slots[1].buffer_state==BufferState::Free);
        assert(core->slots[2].buffer_state==BufferState::Acquired);
        assert(core->broadcasts.load()==frame+1 && event.signals.load()==frame+1);
    }
    assert(delegate->callbacks==260 && delegate->unlocked);
    // Normal single acquire does NOT fabricate a producer-release event.
    core->slots[2].buffer_state=BufferState::Free;
    core->queue.push_back(BufferItem{2,core->slots[2].graphic_buffer,false,1'800'000'000,false});
    BufferItem out{};
    assert(c.AcquireBuffer(&out,std::chrono::nanoseconds{2'000'000'000})==Status::NoError);
    assert(event.signals.load()==260);
    // Deferred frame causes no release callback when nothing was dropped.
    core->slots[2].buffer_state=BufferState::Free;
    core->queue.push_back(BufferItem{2,core->slots[2].graphic_buffer,false,2'500'000'000,false});
    assert(c.AcquireBuffer(&out,std::chrono::nanoseconds{2'000'000'000})==Status::PresentLater);
    assert(event.signals.load()==260);
    core->slots[2].buffer_state=BufferState::Acquired;
    assert(c.AcquireBuffer(&out,std::chrono::nanoseconds{2'000'000'000})==Status::InvalidOperation);
    assert(event.signals.load()==260);
    wake->Stop();
    std::puts("F05_NATIVE_ACQUIRE_DROP_GUEST_WAKE_PASS frames=260 stale_drops=520 "
              "guest_event=260 callbacks_unlocked=1 normal_acquire_quiet=1 "
              "present_later_quiet=1 invalid_quiet=1 scope=source_extracted_mock_kernel");
}
""".replace("__WAKE__", listener).replace("__ACQUIRE__", active)
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f05-acquire-") as folder:
    source = Path(folder) / "acquire.cpp"
    source.write_text(cpp)
    for mode in ("-O0", "-O2"):
        exe = Path(folder) / ("acquire" + mode)
        compile = subprocess.run([compiler,"-std=c++20",mode,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  str(source),"-o",str(exe)],
                                 capture_output=True,text=True,timeout=90)
        assert compile.returncode == 0,(mode,compile.stderr[-6000:])
        run = subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        assert run.returncode == 0,(mode,run.stderr[-6000:],run.stdout)
        assert "F05_NATIVE_ACQUIRE_DROP_GUEST_WAKE_PASS" in run.stdout
        print(mode,run.stdout.strip(),flush=True)
print("F05_REAL_GUEST_IPC_SCHEDULER_AND_FC27_PROGRESS_NOT_PROVEN")
