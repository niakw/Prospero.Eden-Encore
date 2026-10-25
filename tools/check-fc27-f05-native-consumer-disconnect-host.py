#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05 source-extracted consumer disconnect -> Binder KEvent, mock kernel."""
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
old=(root/"vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp").read_text()
new=(root/"vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp").read_text()
producer=(root/"vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
assert 'list(APPEND core_sources "\x24{EDEN_MAINTAINED_NVNF_CONSUMER}")' in cmake
assert 'list(REMOVE_ITEM core_sources "hle/service/nvnflinger/buffer_queue_consumer.cpp")' in cmake
def extract(src, sign):
    assert src.count(sign)==1,sign
    i=src.index(sign); begin=src.index("{",i);depth=0
    for j in range(begin,len(src)):
        if src[j]=="{":depth+=1
        elif src[j]=="}":
            depth-=1
            if depth==0:return src[i:j+1]
    raise AssertionError(sign)
sig="Status BufferQueueConsumer::Disconnect() {"
native=extract(new,sig)
assert "producer_listener->OnBufferReleased();" in native
assert "producer_listener->OnBufferReleased();" not in extract(old,sig)
assert native.index("core->SignalDequeueCondition();")<native.index("producer_listener->OnBufferReleased();")
start="class ProducerReleaseWake final : public IProducerListener {"
assert producer.count(start)==1
i=producer.index(start)
listener=producer[i:producer.index("\n};",i)+3]
cpp=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
#include <utility>
#include <cstdio>
#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
namespace Kernel {
struct KernelCore {};
struct KEvent {
 std::atomic<int> calls{};
 bool closed{};
 void Signal(KernelCore&){assert(!closed);calls.fetch_add(1);}
};
}
namespace Service::android {
enum class Status {NoError,BadValue};
struct IProducerListener {
 virtual ~IProducerListener()=default;
 virtual void OnBufferReleased()=0;
};
struct IConsumerListener {};
struct BufferQueueCore {
 // Test-only timed lock: another awakened host waiter can legitimately
 // acquire the mutex between Disconnect unlocking and the guest callback.
 // A bounded wait distinguishes that contention from callback reentrancy.
 std::timed_mutex mutex{};
 std::condition_variable condition{};
 int epoch{},freed{};
 bool is_abandoned{};
 std::shared_ptr<IConsumerListener> consumer_listener{};
 std::shared_ptr<IProducerListener> connected_producer_listener{};
 std::vector<int> queue{};
 void FreeAllBuffersLocked(){++freed;}
 void SignalDequeueCondition(){++epoch;condition.notify_all();}
};
struct BufferQueueConsumer {
 std::shared_ptr<BufferQueueCore> core;
 explicit BufferQueueConsumer(std::shared_ptr<BufferQueueCore> c):core(std::move(c)){}
 Status Disconnect();
};
__WAKE__
__DISCONNECT__
struct Delegate final : IProducerListener {
 BufferQueueCore& core;
 int called{};
 bool unlocked{};
 explicit Delegate(BufferQueueCore& c):core(c){}
 void OnBufferReleased()override {
  unlocked=core.mutex.try_lock_for(std::chrono::seconds(2));
  if(unlocked)core.mutex.unlock();
  ++called;
 }
};
}
int main(){
 using namespace Service::android;
 Kernel::KernelCore kernel;
 Kernel::KEvent event;
 auto core=std::make_shared<BufferQueueCore>();
 BufferQueueConsumer c(core);
 auto wake=std::make_shared<ProducerReleaseWake>(&event,kernel);
 auto delegate=std::make_shared<Delegate>(*core);
 wake->SetDelegate(delegate);
 core->connected_producer_listener=wake;
 assert(c.Disconnect()==Status::BadValue);
 assert(event.calls.load()==0 && core->epoch==0);
 core->consumer_listener=std::make_shared<IConsumerListener>();
 core->queue.push_back(42);
 std::atomic<int> entered{},finished{};
 auto waiter=[&]{
  std::unique_lock lock(core->mutex);
  auto initial=core->epoch;
  entered.fetch_add(1);
  core->condition.wait(lock,[&]{return core->epoch!=initial;});
  finished.fetch_add(1);
 };
 std::thread a(waiter),b(waiter);
 while(entered.load()!=2)std::this_thread::yield();
 {std::scoped_lock lock(core->mutex);}
 assert(c.Disconnect()==Status::NoError);
 a.join();b.join();
 assert(finished.load()==2 && core->epoch==1 && core->freed==1);
 assert(core->is_abandoned && core->queue.empty());
 assert(!core->connected_producer_listener);
 assert(event.calls.load()==1 && delegate->called==1 && delegate->unlocked);
 assert(c.Disconnect()==Status::BadValue);
 assert(event.calls.load()==1);
 wake->Stop();event.closed=true;wake->OnBufferReleased();
 assert(event.calls.load()==1);
 std::puts("F05_NATIVE_CONSUMER_DISCONNECT_WAKE_PASS host_waiters=2 guest_event=1 callback_unlocked=1 quiet_error=1 safe_stop=1 scope=mock_kernel");
}
""".replace("__WAKE__",listener).replace("__DISCONNECT__",native)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f05-consumer-") as folder:
 src=Path(folder)/"consumer.cpp";src.write_text(cpp)
 for mode in ("-O0","-O2"):
  exe=Path(folder)/("consumer"+mode)
  b=subprocess.run([compiler,"-std=c++20",mode,"-Wall","-Wextra","-Werror","-pthread","-fsanitize=undefined","-fno-sanitize-recover=all",str(src),"-o",str(exe)],capture_output=True,text=True,timeout=90)
  assert b.returncode==0,(mode,b.stderr[-5000:])
  r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
  assert r.returncode==0,(mode,r.stderr[-5000:],r.stdout)
  assert "F05_NATIVE_CONSUMER_DISCONNECT_WAKE_PASS" in r.stdout
  print(mode,r.stdout.strip(),flush=True)
print("F05_REAL_GUEST_HIPC_FC27_LIVENESS_NOT_PROVEN")
