#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05: source-extracted QueueBuffer replacement frees tracked slot, wakes guest.

Runs the actual selected producer's queue replacement and notification block.
Mock core/event and consumer, not guest IPC, GPU or FC27 timing.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
PINNED = (ROOT / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
CMAKE = (ROOT / "headless/CMakeLists.txt").read_text()
assert 'list(APPEND core_sources "\x24{EDEN_MAINTAINED_PROFILE_DEQUEUE}")' in CMAKE

def queue_method(text):
    a = "Status BufferQueueProducer::QueueBuffer("
    b = "\nvoid BufferQueueProducer::CancelBuffer("
    assert text.count(a) == 1 and text.count(b) == 1
    return text[text.index(a):text.index(b,text.index(a))]

active = queue_method(PRODUCER)
pinned = queue_method(PINNED)
start = "        if (core->queue.empty()) {"
end = "        output->Inflate("
assert active.count(start) == 1 and active.count(end) == 1
segment = active[active.index(start):active.index(end)]
wake_start = active.index("    if (recycled_queued_slot) {", active.index(end))
wake_end = active.index("    // Notify consumers with the actual queued item:", wake_start)
wake = active[wake_start:wake_end]
assert "recycled_queued_slot = true;" in segment
assert "buffer_wait_event->Signal(service_context.kernel);" not in segment
assert "buffer_wait_event->Signal(service_context.kernel);" in wake
assert "recycled_queued_slot = true;" not in pinned
assert segment.count("core->SignalDequeueCondition();") == 1
assert wake.count("buffer_wait_event->Signal(service_context.kernel);") == 1
assert active.index("        output->Inflate(") < wake_start

cpp=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <vector>
using u64=std::uint64_t;
enum class BufferState {Free,Queued,Acquired};
struct GraphicBuffer{int id{};};
struct BufferItem{
    int slot{};
    std::shared_ptr<GraphicBuffer> graphic_buffer{};
    u64 frame_number{};
    bool is_droppable{};
};
struct Slot{
    BufferState buffer_state{BufferState::Free};
    u64 frame_number{};
    u64 queue_time{},presentation_time{};
    std::shared_ptr<GraphicBuffer> graphic_buffer{};
};
struct IConsumerListener{};
// Host lock-state model: try_lock on a nonrecursive std::mutex already
// owned by this thread would be UB, so use a tracked atomic lock instead.
struct TrackedMutex {
    std::atomic<bool> held{};
    void lock() {
        bool expected=false;
        assert(held.compare_exchange_strong(expected,true));
    }
    void unlock() { assert(held.exchange(false)); }
    bool try_lock() {
        bool expected=false;
        return held.compare_exchange_strong(expected,true);
    }
};
struct Core {
    TrackedMutex mutex{};
    std::array<Slot,4> slots{};
    std::vector<BufferItem> queue{};
    std::shared_ptr<IConsumerListener> consumer_listener{};
    u64 frame_counter{};
    bool buffer_has_been_queued{};
    std::atomic<int> host_wakes{};
    bool StillTracking(const BufferItem& item)const{
        return item.slot>=0 && item.slot<4 &&
            slots[item.slot].graphic_buffer!=nullptr &&
            slots[item.slot].graphic_buffer==item.graphic_buffer;
    }
    void UpdateHistory(u64,BufferState){}
    void PushHistory(u64,u64,u64,BufferState){}
    void SignalDequeueCondition(){host_wakes.fetch_add(1);}
};
struct Kernel{};
struct Event{
    Core* core{};
    std::atomic<int> guest_wakes{};
    void Signal(Kernel&){
        // This is the critical lock-order regression witness. Guest kernel
        // wake must never be published while BufferQueue mutex is held.
        assert(core->mutex.try_lock());
        core->mutex.unlock();
        guest_wakes.fetch_add(1);
    }
};
struct ServiceContext{Kernel kernel{};};
struct Harness{
    Core core_data{};
    Core* core{&core_data};
    std::array<Slot,4>& slots{core_data.slots};
    ServiceContext service_context{};
    Event event{&core_data};
    Event* buffer_wait_event{&event};
    void Publish(BufferItem item, int slot, bool record_buffer_history=false){
        std::shared_ptr<IConsumerListener> listener_available;
        std::shared_ptr<IConsumerListener> listener_replaced;
        bool recycled_queued_slot=false;
        {
            std::scoped_lock lock{core->mutex};
__PUBLISH__
        }
__WAKE__
        (void)listener_available;(void)listener_replaced;
    }
};
int main(){
    Harness h;
    auto old=std::make_shared<GraphicBuffer>(GraphicBuffer{100});
    auto new_buffer=std::make_shared<GraphicBuffer>(GraphicBuffer{101});
    h.slots[0].graphic_buffer=old;
    h.slots[0].buffer_state=BufferState::Queued;
    h.Publish(BufferItem{0,old,1,false},0);
    assert(h.core->queue.size()==1 && h.event.guest_wakes.load()==0);
    h.Publish(BufferItem{1,new_buffer,2,false},1);
    assert(h.core->queue.size()==2 && h.event.guest_wakes.load()==0);
    h.core->queue.clear();
    h.core->queue.push_back(BufferItem{0,old,1,true});
    h.Publish(BufferItem{1,new_buffer,3,false},1);
    assert(h.core->queue.size()==1 && h.core->queue.front().graphic_buffer==new_buffer);
    assert(h.slots[0].buffer_state==BufferState::Free);
    assert(h.event.guest_wakes.load()==1);
    // A queued frame no longer tracked in slots may be replaced, but it
    // cannot create a new reusable slot or a spurious guest wake.
    h.core->queue.clear();
    h.core->queue.push_back(BufferItem{0,old,4,true});
    h.slots[0].graphic_buffer=std::make_shared<GraphicBuffer>(GraphicBuffer{404});
    h.Publish(BufferItem{1,new_buffer,5,false},1);
    assert(h.event.guest_wakes.load()==1);
    // One guest event per freed queued slot even under frame replacement
    // bursts. The non-droppable path remains a normal queue append.
    for(int cycle=0;cycle<260;++cycle){
        h.core->queue.clear();
        h.slots[0].graphic_buffer=old;
        h.slots[0].buffer_state=BufferState::Queued;
        h.core->queue.push_back(BufferItem{0,old,(u64)cycle,true});
        h.Publish(BufferItem{1,new_buffer,(u64)cycle+1,false},1);
        assert(h.core->queue.size()==1 && h.slots[0].buffer_state==BufferState::Free);
    }
    assert(h.event.guest_wakes.load()==261);
    assert(h.core->host_wakes.load()==264);
    std::puts("F05_NATIVE_QUEUE_REPLACEMENT_GUEST_WAKE_PASS replacements=260 "
              "tracked_release_signal=1 untracked_quiet=1 regular_enqueue_quiet=1 "
              "callback_unlocked=1 scope=source_extracted_mock_guest_event");
}
""".replace("__PUBLISH__",segment).replace("__WAKE__",wake)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"host C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f05-queue-replace-") as tmp:
    source=Path(tmp)/"queue.cpp"
    source.write_text(cpp)
    for mode in ("-O0","-O2"):
        exe=Path(tmp)/("queue"+mode)
        b=subprocess.run([compiler,"-std=c++20",mode,"-Wall","-Wextra","-Werror",
                          "-fsanitize=undefined","-fno-sanitize-recover=all",
                          str(source),"-o",str(exe)],capture_output=True,text=True,timeout=90)
        assert b.returncode==0,(mode,b.stderr[-6000:])
        r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        assert r.returncode==0,(mode,r.stderr[-6000:],r.stdout)
        assert "F05_NATIVE_QUEUE_REPLACEMENT_GUEST_WAKE_PASS" in r.stdout
        print(mode,r.stdout.strip(),flush=True)
print("F05_HIPC_SCHEDULING_AND_FC27_FRAME_PROGRESS_NOT_PROVEN")
