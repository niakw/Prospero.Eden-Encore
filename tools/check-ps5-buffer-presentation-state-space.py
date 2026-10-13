#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Enumerate guest presentation states using the EXACT upstream AcquireBuffer C++ body.

This verifies a dead candidate fix rather than misleadingly green-lighting a
native hardware test. Compiles original source and counterfactual attempted
fix, compares all externally visible queue and slot outcomes across 333,333
combinations: 0-5 frames, temporal orderings, automatic timestamps, 3 deadlines.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
consumer_path = root / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp"
consumer = consumer_path.read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
assert "eden_dropped_queued_buffer" not in cmake, "Do not ship unreachable deferred-drop wake"
start = consumer.index("Status BufferQueueConsumer::AcquireBuffer(")
end = consumer.index("\nStatus BufferQueueConsumer::ReleaseBuffer(", start)
original = consumer[start:end]
counterfactual = original
edits = [
    ("    auto front(core->queue.begin());\n\n    // If expected_present is specified,",
     "    auto front(core->queue.begin());\n    bool eden_dropped_queued_buffer = false;\n\n    // If expected_present is specified,"),
    ("            core->queue.erase(front);\n            front = core->queue.begin();",
     "            core->queue.erase(front);\n            eden_dropped_queued_buffer = true;\n            front = core->queue.begin();"),
    ("            return Status::PresentLater;",
     "            if (eden_dropped_queued_buffer) core->SignalDequeueCondition();\n            return Status::PresentLater;")
]
for target, patch in edits:
    assert counterfactual.count(target) == 1, "native source anchor drifted"
    counterfactual = counterfactual.replace(target, patch)
original = original.replace("BufferQueueConsumer::AcquireBuffer(", "OriginalConsumer::AcquireBuffer(")
counterfactual = counterfactual.replace("BufferQueueConsumer::AcquireBuffer(", "DerivedConsumer::AcquireBuffer(")
fixture = r"""#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <vector>
using s32=std::int32_t;using s64=std::int64_t;using u64=std::uint64_t;
#define LOG_ERROR(...) ((void)0)
#define LOG_DEBUG(...) ((void)0)
namespace Service::android {
enum class BufferState { Free, Dequeued, Queued, Acquired };
enum class Status { NoError, InvalidOperation, NoBufferAvailable, PresentLater };
struct GraphicBuffer{};
struct BufferItem{std::shared_ptr<GraphicBuffer> graphic_buffer; s64 timestamp{}; bool is_auto_timestamp{};s32 slot{-1};bool acquire_called{};};
struct BufferSlot{std::shared_ptr<GraphicBuffer> graphic_buffer;BufferState buffer_state{BufferState::Free};bool acquire_called{};bool needs_cleanup_on_release{};};
class BufferQueueCore {
public:
 std::mutex mutex;std::array<BufferSlot,64> slots{};std::vector<BufferItem> queue;
 const s32 max_acquired_buffer_count=0;unsigned notifications=0;
 bool StillTracking(const BufferItem& item)const {
   return item.slot>=0 && item.slot<64 && item.graphic_buffer && slots[item.slot].graphic_buffer==item.graphic_buffer;
 }
 void SignalDequeueCondition(){++notifications;}
};
struct OriginalConsumer {
 std::shared_ptr<BufferQueueCore> core;std::array<BufferSlot,64>&slots;
 explicit OriginalConsumer(std::shared_ptr<BufferQueueCore> c):core(c),slots(c->slots){}
 Status AcquireBuffer(BufferItem*,std::chrono::nanoseconds);
};
struct DerivedConsumer{
 std::shared_ptr<BufferQueueCore> core;std::array<BufferSlot,64>&slots;
 explicit DerivedConsumer(std::shared_ptr<BufferQueueCore> c):core(c),slots(c->slots){}
 Status AcquireBuffer(BufferItem*,std::chrono::nanoseconds);
};

__ORIGINAL__
__DERIVED__
struct Outcome{Status status{};unsigned notifications{};unsigned queue_left{};unsigned free_slots{};unsigned acquired_slots{};s32 acquired_slot{-1};};
template<class Consumer>
Outcome Run(unsigned n,unsigned mask,unsigned auto_bits,unsigned expected_index){
 constexpr s64 values[]={-2000000000LL,-500000000LL,0,500000000LL,2000000000LL};
 constexpr s64 expected[]={250000000LL,750000000LL,1500000000LL};
 auto core=std::make_shared<BufferQueueCore>();
 for(unsigned i=0;i<n;i++){
   auto b=std::make_shared<GraphicBuffer>();auto index=mask%5;mask/=5;
   core->slots[i].graphic_buffer=b;core->slots[i].buffer_state=BufferState::Queued;
   core->queue.push_back(BufferItem{b,values[index],(auto_bits&(1u<<i))!=0,static_cast<s32>(i),false});
 }
 Consumer cons(core);BufferItem out{};
 Status st=cons.AcquireBuffer(&out,std::chrono::nanoseconds(expected[expected_index]));
 Outcome result;result.status=st;result.notifications=core->notifications;
 result.queue_left=static_cast<unsigned>(core->queue.size());result.acquired_slot=out.slot;
 for(unsigned i=0;i<n;i++){result.free_slots+=core->slots[i].buffer_state==BufferState::Free;result.acquired_slots+=core->slots[i].buffer_state==BufferState::Acquired;}
 return result;
}
bool Same(const Outcome&a,const Outcome&b){
 return a.status==b.status&&a.notifications==b.notifications&&a.queue_left==b.queue_left&&a.free_slots==b.free_slots&&a.acquired_slots==b.acquired_slots&&a.acquired_slot==b.acquired_slot;
}
int main(){
 unsigned long long runs=0, deferred=0, accepted=0, deferred_after_drop=0;
 for(unsigned n=0;n<=5;++n){
   unsigned max=1;for(unsigned j=0;j<n;j++)max*=5;
   for(unsigned i=0;i<max;i++)
    for(unsigned ab=0;ab<(1u<<n);ab++)
     for(unsigned expected=0;expected<3;expected++){
       const auto a=Run<OriginalConsumer>(n,i,ab,expected);
       const auto b=Run<DerivedConsumer>(n,i,ab,expected);
       assert(Same(a,b)&&"Existing PresentLater patch changes observable behavior");
       ++runs;
       if(a.status==Status::PresentLater){
         deferred++;
         if(a.queue_left<n)deferred_after_drop++;
         assert(a.notifications==0);
       }
       if(a.status==Status::NoError){accepted++;assert(a.notifications==1);}
     }
 }
 assert(deferred>0 && accepted>0 && deferred_after_drop==0);
 std::printf("PASS %llu exact-source state cases; presented=%llu deferred=%llu deferred_after_drop=%llu\n",runs,accepted,deferred,deferred_after_drop);
 std::puts("INVARIANT: original and native-derived have IDENTICAL outcomes; deferred drop wake condition never occurs."); return 0;
}
} // namespace Service::android
int main(){return Service::android::main();}

"""
fixture = fixture.replace("__ORIGINAL__", original).replace("__DERIVED__", counterfactual)
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-guest-present-state-") as tmp:
    source = Path(tmp) / "presentation.cpp"
    executable = Path(tmp) / "presentation"
    source.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread", "-Wall",
                    "-Wextra", "-Werror", str(source), "-o", str(executable)],
                   check=True, timeout=60)
    subprocess.run([str(executable)], check=True, timeout=50)
print("PASS: exact C++ guest AcquireBuffer state space; no emulated FPS or console claim")
