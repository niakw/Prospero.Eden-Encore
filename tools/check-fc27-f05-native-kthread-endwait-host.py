#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05: shipping Binder release -> native KThread wait queue EndWait.

Source-extracts the actual kernel waiter and queue methods into a C++20
fixture. The kernel scheduler, process handle table, guest CPU, IPC call and
FC27 are mocked/not executed. This is *host* source-path evidence only.
"""
from pathlib import Path
import shutil, subprocess, tempfile

root=Path(__file__).resolve().parents[1]
src=root/"vendor/sources/eden/src/core/hle/kernel"
producer=(root/"vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
event=(src/"k_event.cpp").read_text()
readable=(src/"k_readable_event.cpp").read_text()
sync=(src/"k_synchronization_object.cpp").read_text()
thread=(src/"k_thread.cpp").read_text()
queue=(src/"k_thread_queue.cpp").read_text()
sync_header=(src/"k_synchronization_object.h").read_text()
binder=(root/"vendor/sources/eden/src/core/hle/service/nvnflinger/hos_binder_driver.cpp").read_text()
assert "return &buffer_wait_event->GetReadableEvent();" in producer
assert "*out_handle = binder->GetNativeHandle(type_id);" in binder

def native(text,signature):
    assert text.count(signature)==1,("source drift",signature)
    start=text.index(signature);a=text.index("{",start);depth=0
    for i in range(a,len(text)):
        if text[i]=="{":depth+=1
        elif text[i]=="}":
            depth-=1
            if depth==0:return text[start:i+1]
    raise AssertionError(signature)

start="class ThreadQueueImplForKSynchronizationObjectWait final : public KThreadQueueWithoutEndWait {"
assert sync.count(start)==1
i=sync.index(start)
wait_impl=sync[i:sync.index("\n};",i)+3]
assert "KThreadQueue::EndWait(kernel, waiting_thread, wait_result);" in wait_impl
assert "m_objects[i]->UnlinkNode(std::addressof(m_nodes[i]));" in wait_impl
start="class ProducerReleaseWake final : public IProducerListener {"
assert producer.count(start)==1
i=producer.index(start)
listener=producer[i:producer.index("\n};",i)+3]
assert "event->Signal(kernel);" in listener
methods={
"__EVENT_SIGNAL__":native(event,"Result KEvent::Signal(KernelCore& kernel)"),
"__READABLE_SIGNAL__":native(readable,"Result KReadableEvent::Signal(KernelCore& kernel)"),
"__READABLE_RESET__":native(readable,"Result KReadableEvent::Reset(KernelCore& kernel)"),
"__READABLE_IS_SIGNALED__":native(readable,"bool KReadableEvent::IsSignaled(KernelCore& kernel) const"),
"__SYNC_NOTIFY__":native(sync,"void KSynchronizationObject::NotifyAvailable(KernelCore& kernel, Result result)"),
"__THREAD_BEGIN__":native(thread,"void KThread::BeginWait(KernelCore& kernel, KThreadQueue* queue)"),
"__THREAD_NOTIFY__":native(thread,"void KThread::NotifyAvailable(KernelCore& kernel, KSynchronizationObject* signaled_object, Result wait_result)"),
"__QUEUE_END__":native(queue,"void KThreadQueue::EndWait(KernelCore& kernel, KThread* waiting_thread, Result wait_result)"),
"__QUEUE_CANCEL__":native(queue,"void KThreadQueue::CancelWait(KernelCore& kernel, KThread* waiting_thread, Result wait_result, bool cancel_timer_task)"),
"__WAIT_IMPL__":wait_impl,
"__RELEASE_WAKE__":listener,
}
assert 'waiting_thread->SetState(kernel, ThreadState::Runnable);' in methods["__QUEUE_END__"]
assert 'm_wait_queue->NotifyAvailable(kernel, this, signaled_object, wait_result);' in methods["__THREAD_NOTIFY__"]

cpp=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#define ASSERT(x) assert(x)
#define ASSERT_MSG(...) assert(false)
using s32=std::int32_t;
namespace Kernel {
enum class Result{Success,InvalidState};
[[maybe_unused]] constexpr Result ResultSuccess=Result::Success;
constexpr Result ResultInvalidState=Result::InvalidState;
#define R_SUCCEED() return Result::Success
#define R_SUCCEED_IF(x) if(x) return Result::Success
#define R_UNLESS(x,r) if(!(x)) return r
struct KernelCore {std::recursive_mutex scheduler_mutex{};};
struct KScopedSchedulerLock {
 std::scoped_lock<std::recursive_mutex> lock;
 explicit KScopedSchedulerLock(KernelCore& k):lock(k.scheduler_mutex){}
};
struct KScheduler {
 static bool IsSchedulerLockedByCurrentThread(KernelCore&){return true;}
};
enum class ThreadState{Runnable,Waiting};
class KSynchronizationObject;
class KThread;
struct KHardwareTimer {
 int cancelled{};
 void CancelTask(KThread*){++cancelled;}
};
class KThreadQueue {
protected:
 KHardwareTimer* m_hardware_timer{};
public:
 explicit KThreadQueue(KernelCore&){}
 virtual ~KThreadQueue()=default;
 void SetHardwareTimer(KHardwareTimer* timer){m_hardware_timer=timer;}
 virtual void NotifyAvailable(KernelCore&,KThread*,KSynchronizationObject*,Result)=0;
 virtual void CancelWait(KernelCore&,KThread*,Result,bool);
 virtual void EndWait(KernelCore&,KThread*,Result);
};
class KThreadQueueWithoutEndWait:public KThreadQueue {
public:
 explicit KThreadQueueWithoutEndWait(KernelCore& k):KThreadQueue(k){}
 // Only the NotifyAvailable override calls KThreadQueue::EndWait;
 // this override remains unreachable in normal synchronization.
 void EndWait(KernelCore&,KThread*,Result) override{assert(false);}
};
class KThread {
 ThreadState state{ThreadState::Runnable};
 KThreadQueue* m_wait_queue{};
 Result result{Result::InvalidState};
 int synced_index{-1};
 bool cancellable{};
 int state_transitions{};
public:
 ThreadState GetState()const{return state;}
 void SetState(KernelCore&,ThreadState next){state=next;++state_transitions;}
 void SetWaitResult(Result next){result=next;}
 Result GetWaitResult()const{return result;}
 void ClearWaitQueue(){m_wait_queue=nullptr;}
 bool HasWaitQueue()const{return m_wait_queue!=nullptr;}
 void SetSyncedIndex(int i){synced_index=i;}
 int GetSyncedIndex()const{return synced_index;}
 void SetCancellable(){cancellable=true;}
 void ClearCancellable(){cancellable=false;}
 bool IsCancellable()const{return cancellable;}
 int Transitions()const{return state_transitions;}
 void BeginWait(KernelCore&,KThreadQueue*);
 void NotifyAvailable(KernelCore&,KSynchronizationObject*,Result);
};
class KSynchronizationObject {
public:
 struct ThreadListNode {ThreadListNode* next{};KThread* thread{};};
 ThreadListNode* m_thread_list_head{};
 ThreadListNode* m_thread_list_tail{};
 virtual ~KSynchronizationObject()=default;
 virtual bool IsSignaled(KernelCore&)const=0;
 void LinkNode(ThreadListNode* node) {
  if(m_thread_list_tail==nullptr)m_thread_list_head=node;
  else m_thread_list_tail->next=node;
  m_thread_list_tail=node;
 }
 void UnlinkNode(ThreadListNode* node) {
  ThreadListNode* prev_ptr=reinterpret_cast<ThreadListNode*>(&m_thread_list_head);
  ThreadListNode* prev_val=nullptr;
  ThreadListNode *prev,*tail_prev;
  do{
   prev=prev_ptr;prev_ptr=prev_ptr->next;tail_prev=prev_val;prev_val=prev_ptr;
   assert(prev_ptr && "unlinking a node that was not linked");
  }while(prev_ptr!=node);
  if(m_thread_list_tail==node)m_thread_list_tail=tail_prev;
  prev->next=node->next;
 }
 void NotifyAvailable(KernelCore&,Result);
 void NotifyAvailable(KernelCore& k){NotifyAvailable(k,Result::Success);}
 int WaitingCount()const{
  int n=0;for(auto* p=m_thread_list_head;p;p=p->next)++n;
  return n;
 }
};
class KReadableEvent final:public KSynchronizationObject {
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
__QUEUE_END__
__QUEUE_CANCEL__
__THREAD_BEGIN__
__THREAD_NOTIFY__
__SYNC_NOTIFY__
__READABLE_IS_SIGNALED__
__READABLE_SIGNAL__
__READABLE_RESET__
__EVENT_SIGNAL__
__WAIT_IMPL__
}
namespace Service::android {
class IProducerListener{
public:virtual ~IProducerListener()=default;virtual void OnBufferReleased()=0;
};
__RELEASE_WAKE__
}
int main(){
 Kernel::KernelCore kernel;
 Kernel::KEvent event;
 auto& readable=event.GetReadableEvent();
 Kernel::KThread guest_game,guest_hud;
 auto wake=std::make_shared<Service::android::ProducerReleaseWake>(&event,kernel);
 Kernel::KHardwareTimer timer;
 int guest_resumptions{};
 for(int frame=0;frame<260;++frame){
  Kernel::KSynchronizationObject* wait_game_objects[]{&readable};
  Kernel::KSynchronizationObject* wait_hud_objects[]{&readable};
  Kernel::KSynchronizationObject::ThreadListNode game_node{nullptr,&guest_game};
  Kernel::KSynchronizationObject::ThreadListNode hud_node{nullptr,&guest_hud};
  Kernel::ThreadQueueImplForKSynchronizationObjectWait
      game_wait(kernel,wait_game_objects,&game_node,1),
      hud_wait(kernel,wait_hud_objects,&hud_node,1);
  game_wait.SetHardwareTimer(&timer);
  hud_wait.SetHardwareTimer(&timer);
  {
   Kernel::KScopedSchedulerLock lock{kernel};
   assert(!readable.IsSignaled(kernel));
   readable.LinkNode(&game_node);
   readable.LinkNode(&hud_node);
   guest_game.BeginWait(kernel,&game_wait);
   guest_hud.BeginWait(kernel,&hud_wait);
   guest_game.SetCancellable();
   guest_hud.SetCancellable();
   assert(readable.WaitingCount()==2);
  }
  wake->OnBufferReleased(); // release -> KEvent -> readable -> KThread -> EndWait
  assert(guest_game.GetState()==Kernel::ThreadState::Runnable);
  assert(guest_hud.GetState()==Kernel::ThreadState::Runnable);
  assert(!guest_game.HasWaitQueue() && !guest_hud.HasWaitQueue());
  assert(!guest_game.IsCancellable() && !guest_hud.IsCancellable());
  assert(guest_game.GetWaitResult()==Kernel::Result::Success);
  assert(guest_hud.GetWaitResult()==Kernel::Result::Success);
  assert(guest_game.GetSyncedIndex()==0 && guest_hud.GetSyncedIndex()==0);
  assert(readable.WaitingCount()==0);
  guest_resumptions+=2;
  wake->OnBufferReleased(); // signaled level: no spurious duplicate resume
  assert(timer.cancelled==(frame+1)*2);
  assert(readable.Reset(kernel)==Kernel::Result::Success);
  assert(readable.Reset(kernel)==Kernel::Result::InvalidState);
 }
 assert(guest_resumptions==520);
 assert(guest_game.Transitions()==520 && guest_hud.Transitions()==520);
 assert(timer.cancelled==520);
 wake->Stop();wake->OnBufferReleased();
 assert(readable.WaitingCount()==0);
 std::puts("F05_NATIVE_KTHREAD_ENDWAIT_PASS cycles=260 resumed_game=260 "
           "resumed_hud=260 wait_nodes_unlinked=1 runnable_state=1 "
           "timer_cancelled=520 level_coalescing=1 safe_stop=1 "
           "scope=source_extracted_kthread_queue_mock_scheduler");
}
"""
for name,impl in methods.items():
    assert cpp.count(name)==1,(name,cpp.count(name))
    cpp=cpp.replace(name,impl)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 host compiler needed"
with tempfile.TemporaryDirectory(prefix="encore-f05-endwait-") as td:
 source=Path(td)/"wait.cpp";source.write_text(cpp)
 for mode in ("-O0","-O2"):
  exe=Path(td)/("wait"+mode)
  b=subprocess.run([compiler,"-std=c++20",mode,"-Wall","-Wextra","-Werror",
                    "-fsanitize=undefined","-fno-sanitize-recover=all",
                    str(source),"-o",str(exe)],
                   capture_output=True,text=True,timeout=90)
  assert b.returncode==0,(mode,b.stderr[-7500:])
  r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
  assert r.returncode==0,(mode,r.stderr[-7500:],r.stdout)
  assert "F05_NATIVE_KTHREAD_ENDWAIT_PASS cycles=260" in r.stdout
  print(mode,r.stdout.strip(),flush=True)
print("F05_REAL_GUEST_SCHEDULER_AND_FC27_LIVENESS_NOT_PROVEN")
