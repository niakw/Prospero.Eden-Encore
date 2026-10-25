#!/usr/bin/env python3
"""F05 shipping release listener -> KEvent -> readable notifier -> mock guest waits.

Extracts actual C++ methods. Host KThread/kernel scheduler remain mocks, so
this is NOT a game scheduler, HIPC read, Vulkan GPU or FC27 proof.
"""
from pathlib import Path
import shutil, subprocess, tempfile

root=Path(__file__).resolve().parents[1]
k=root/"vendor/sources/eden/src/core/hle/kernel"
producer=(root/"vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
event=(k/"k_event.cpp").read_text()
readable=(k/"k_readable_event.cpp").read_text()
sync=(k/"k_synchronization_object.cpp").read_text()
binder=(root/"vendor/sources/eden/src/core/hle/service/nvnflinger/hos_binder_driver.cpp").read_text()
svcs=(k/"svc/svc_synchronization.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
assert "EDEN_MAINTAINED_PROFILE_DEQUEUE" in cmake
assert "return &buffer_wait_event->GetReadableEvent();" in producer
assert "*out_handle = binder->GetNativeHandle(type_id);" in binder
assert "KSynchronizationObject::Wait(system.Kernel()" in svcs

def native(src,sig):
    assert src.count(sig)==1,sig
    start=src.index(sig);op=src.index("{",start);depth=0
    for i in range(op,len(src)):
        if src[i]=="{":depth+=1
        elif src[i]=="}":
            depth-=1
            if depth==0:return src[start:i+1]
    raise AssertionError(sig)

methods={
 "__KS_NOTIFY__":native(sync,"void KSynchronizationObject::NotifyAvailable(KernelCore& kernel, Result result)"),
 "__READABLE_CHECK__":native(readable,"bool KReadableEvent::IsSignaled(KernelCore& kernel) const"),
 "__READABLE_SIGNAL__":native(readable,"Result KReadableEvent::Signal(KernelCore& kernel)"),
 "__READABLE_RESET__":native(readable,"Result KReadableEvent::Reset(KernelCore& kernel)"),
 "__EVENT_SIGNAL__":native(event,"Result KEvent::Signal(KernelCore& kernel)"),
}
start="class ProducerReleaseWake final : public IProducerListener {"
assert producer.count(start)==1
at=producer.index(start)
methods["__RELEASE_WAKE__"]=producer[at:producer.index("\n};",at)+3]
assert "event->Signal(kernel);" in methods["__RELEASE_WAKE__"]
assert "this->NotifyAvailable(kernel);" in methods["__READABLE_SIGNAL__"]
assert "cur_node->thread->NotifyAvailable(kernel, this, result);" in methods["__KS_NOTIFY__"]

cpp=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <memory>
#include <mutex>
#include <thread>
#define ASSERT(x) assert(x)
namespace Kernel {
enum class Result {Success,InvalidState};
constexpr Result ResultSuccess=Result::Success;
constexpr Result ResultInvalidState=Result::InvalidState;
#define R_SUCCEED() return Result::Success
#define R_SUCCEED_IF(x) if(x) return Result::Success
#define R_UNLESS(x,r) if(!(x)) return r
struct KernelCore {std::recursive_mutex scheduler_lock{};};
struct KScopedSchedulerLock {
 std::scoped_lock<std::recursive_mutex> lock;
 explicit KScopedSchedulerLock(KernelCore& k):lock(k.scheduler_lock){}
};
struct KScheduler {
 static bool IsSchedulerLockedByCurrentThread(KernelCore&){return true;}
};
class KSynchronizationObject;
class KThread {
 std::mutex mutex{};
 std::condition_variable cv{};
 int count{};
public:
 void NotifyAvailable(KernelCore&,KSynchronizationObject*,Result r){
  assert(r==Result::Success);
  {std::scoped_lock lock{mutex};++count;}
  cv.notify_all();
 }
 bool WaitUntil(int target){
  std::unique_lock lock{mutex};
  return cv.wait_for(lock,std::chrono::seconds(5),[&]{return count>=target;});
 }
 int Count(){std::scoped_lock lock{mutex};return count;}
};
class KSynchronizationObject {
public:
 struct ThreadListNode {ThreadListNode* next{};KThread* thread{};};
 ThreadListNode* m_thread_list_head{};
 ThreadListNode* m_thread_list_tail{};
 void LinkNode(ThreadListNode* n){
  if(!m_thread_list_tail)m_thread_list_head=n;
  else m_thread_list_tail->next=n;
  m_thread_list_tail=n;
 }
 virtual ~KSynchronizationObject()=default;
 virtual bool IsSignaled(KernelCore&)const=0;
 void NotifyAvailable(KernelCore&,Result);
 void NotifyAvailable(KernelCore& k){NotifyAvailable(k,Result::Success);}
};
class KReadableEvent final : public KSynchronizationObject {
 bool m_is_signaled{};
public:
 bool IsSignaled(KernelCore&)const override;
 Result Signal(KernelCore&);
 Result Reset(KernelCore&);
};
class KEvent {
 KReadableEvent m_readable_event{};
 bool m_readable_event_destroyed{};
public:
 KReadableEvent& GetReadableEvent(){return m_readable_event;}
 Result Signal(KernelCore&);
};
__KS_NOTIFY__
__READABLE_CHECK__
__READABLE_SIGNAL__
__READABLE_RESET__
__EVENT_SIGNAL__
}
namespace Service::android {
class IProducerListener {
public:
 virtual ~IProducerListener()=default;
 virtual void OnBufferReleased()=0;
};
__RELEASE_WAKE__
}
int main(){
 Kernel::KernelCore kernel;
 Kernel::KEvent event;
 auto& readable=event.GetReadableEvent();
 Kernel::KThread t1,t2;
 Kernel::KSynchronizationObject::ThreadListNode n1{nullptr,&t1},n2{nullptr,&t2};
 {Kernel::KScopedSchedulerLock lock{kernel};
  readable.LinkNode(&n1);readable.LinkNode(&n2);
  assert(!readable.IsSignaled(kernel));}
 auto wake=std::make_shared<Service::android::ProducerReleaseWake>(&event,kernel);
 std::atomic<int> resumed{};
 std::thread a([&]{for(int i=1;i<=260;++i){assert(t1.WaitUntil(i));resumed.fetch_add(1);}});
 std::thread b([&]{for(int i=1;i<=260;++i){assert(t2.WaitUntil(i));resumed.fetch_add(1);}});
 for(int i=1;i<=260;++i){
  wake->OnBufferReleased();
  wake->OnBufferReleased(); // signaled event is level, not queued tokens
  while(resumed.load()<i*2)std::this_thread::yield();
  assert(t1.Count()==i && t2.Count()==i);
  {Kernel::KScopedSchedulerLock lock{kernel};assert(readable.IsSignaled(kernel));}
  assert(readable.Reset(kernel)==Kernel::Result::Success);
  assert(readable.Reset(kernel)==Kernel::Result::InvalidState);
 }
 a.join();b.join();
 assert(resumed.load()==520);
 wake->Stop();wake->OnBufferReleased();
 assert(t1.Count()==260 && t2.Count()==260);
 std::puts("F05_NATIVE_KERNEL_GUEST_WAIT_WAKE_PASS cycles=260 mock_guest_threads=2 "
           "resumptions=520 coalesced_signals=260 reset_rearms=260 "
           "safe_stop=1 scope=shipping_event_methods_mock_scheduler");
}
"""
for k,v in methods.items():
    assert cpp.count(k)==1,k
    cpp=cpp.replace(k,v)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"host compiler needed"
with tempfile.TemporaryDirectory(prefix="encore-f05-kernel-") as folder:
 src=Path(folder)/"kernel.cpp";src.write_text(cpp)
 for opt in ("-O0","-O2"):
  exe=Path(folder)/("kernel"+opt)
  build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-pthread","-fsanitize=undefined","-fno-sanitize-recover=all",
                        str(src),"-o",str(exe)],capture_output=True,text=True,timeout=90)
  assert build.returncode==0,(opt,build.stderr[-5000:])
  run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
  assert run.returncode==0,(opt,run.stderr[-5000:],run.stdout)
  assert "F05_NATIVE_KERNEL_GUEST_WAIT_WAKE_PASS" in run.stdout
  print(opt,run.stdout.strip(),flush=True)
print("F05_NATIVE_GUEST_KTHREAD_ENDWAIT_AND_FC27_LIVENESS_NOT_PROVEN")
