#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-derived host contract for address signal -> queue -> runnable transition.

Runs actual pinned/native Signal, KThread BeginWait/EndWait/SetState, and
KThreadQueue EndWait against minimal host state/tree/timer fixtures.
This proves nominal state transitions, not a real console's guest/JIT progress.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
pinned = (root/"vendor/sources/eden/src/core/hle/kernel/k_address_arbiter.cpp").read_text()
active = (root/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_address_arbiter.cpp").read_text()
thread = (root/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.cpp").read_text()
queue = (root/"vendor/sources/eden/src/core/hle/kernel/k_thread_queue.cpp").read_text()
cmake = (root/"headless/CMakeLists.txt").read_text()
workflow = (root/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/verify/hle/check-native-hle-address-wake-host.py" in workflow
module = (root/"vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
assert "native-hle-overrides.cmake" in cmake
assert "k_address_arbiter.cpp" in module and "k_thread.cpp" in module
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler

def source_body(code, begin, end):
    assert code.count(begin) == 1 and code.count(end) == 1
    return begin + code.split(begin, 1)[1].split(end, 1)[0].rstrip() + "\n\n"

begin = "Result KAddressArbiter::Signal(uint64_t addr, s32 count) {"
end = "Result KAddressArbiter::SignalAndIncrementIfEqual("
signal = source_body(active, begin, end)
assert signal == source_body(pinned, begin, end)
methods = "\n".join([
    source_body(thread,"void KThread::BeginWait(","void KThread::NotifyAvailable("),
    source_body(thread,"void KThread::EndWait(","void KThread::CancelWait("),
    source_body(thread,"void KThread::SetState(","std::shared_ptr<Common::Fiber>& KThread::GetHostContext("),
    source_body(queue,"void KThreadQueue::EndWait(","void KThreadQueue::CancelWait("),
    signal,
])
header = r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <list>
#include <memory>
#include <vector>
using u32=std::uint32_t;
using s32=std::int32_t;
using u64=std::uint64_t;
namespace Kernel {
using Result=int;
constexpr Result ResultSuccess=0;
#define R_SUCCEED() return ResultSuccess
#define ASSERT(x) assert(x)
#define ASSERT_MSG(x,message) assert(x)
enum class ThreadState:u32 {Runnable=1,Waiting=2,Mask=3};
ThreadState operator~(ThreadState s){return static_cast<ThreadState>(~static_cast<u32>(s));}
ThreadState operator&(ThreadState a,ThreadState b){
 return static_cast<ThreadState>(static_cast<u32>(a)&static_cast<u32>(b));}
ThreadState operator|(ThreadState a,ThreadState b){
 return static_cast<ThreadState>(static_cast<u32>(a)|static_cast<u32>(b));}
struct KThread;
struct KernelCore {int depth{},began{},resumed{};};
struct KScopedSchedulerLock {
 KernelCore& k;
 explicit KScopedSchedulerLock(KernelCore& x):k(x){++k.depth;}
 ~KScopedSchedulerLock(){--k.depth;}
};
struct KHardwareTimer {
 std::vector<KThread*> cancelled;
 void CancelTask(KThread* t){cancelled.push_back(t);}
};
struct KThreadQueue {
 KHardwareTimer* m_hardware_timer{};
 explicit KThreadQueue(KernelCore&){}
 virtual ~KThreadQueue()=default;
 void SetHardwareTimer(KHardwareTimer* t){m_hardware_timer=t;}
 virtual void EndWait(KernelCore&,KThread*,Result);
};
struct KThread {
 std::atomic<ThreadState> m_thread_state{ThreadState::Runnable};
 KThreadQueue* m_wait_queue{};
 Result result{-1};
 u64 key{};
 bool arbitration{};
 void SetWaitReasonForDebugging(int){}
 ThreadState GetState() const {return m_thread_state.load() & ThreadState::Mask;}
 void SetWaitResult(Result x){result=x;}
 void SetState(KernelCore&,ThreadState);
 void BeginWait(KernelCore&,KThreadQueue*);
 void EndWait(KernelCore&,Result);
 void ClearWaitQueue(){m_wait_queue=nullptr;}
 u64 GetAddressArbiterKey() const{return key;}
 bool IsWaitingForAddressArbiter() const{return arbitration;}
 void ClearAddressArbiter(){arbitration=false;}
};
struct KScheduler {
 static void OnThreadStateChanged(KernelCore& k,KThread* t,ThreadState old){
  assert(k.depth>0);
  if(old==ThreadState::Runnable && t->GetState()==ThreadState::Waiting)++k.began;
  else if(old==ThreadState::Waiting && t->GetState()==ThreadState::Runnable)++k.resumed;
  else assert(false && "unexpected HLE state transition");
 }
};
struct ThreadTree {
 struct Key {u64 address;int priority;};
 std::list<KThread*> entries;
 struct It {
  std::list<KThread*>::iterator cursor;
  KThread& operator*()const{return **cursor;}
  KThread* operator->()const{return *cursor;}
  bool operator!=(const It& b)const{return cursor!=b.cursor;}
 };
 It nfind_key(Key key) {
  return {std::find_if(entries.begin(),entries.end(),
          [&](KThread* t){return t->key>=key.address;})};
 }
 It end(){return {entries.end()};}
 It erase(It it){return {entries.erase(it.cursor)};}
 void insert(KThread& t){
  auto it=std::find_if(entries.begin(),entries.end(),
             [&](KThread* x){return x->key>t.key;});
  entries.insert(it,&t);
 }
 std::size_t size()const{return entries.size();}
};
}
namespace Core {
struct System {
 Kernel::KernelCore& core;
 Kernel::KernelCore& Kernel(){return core;}
};
}
namespace Kernel {
struct KAddressArbiter {
 ThreadTree m_tree;
 Core::System& system;
 explicit KAddressArbiter(Core::System& s):system(s){}
 Result Signal(u64 addr,s32 count);
};
"""
footer = r"""
} // namespace Kernel
int main(){
 using namespace Kernel;
 KernelCore k;
 Core::System system{k};
 KAddressArbiter a{system};
 KHardwareTimer timer;
 KThreadQueue q{k};
 q.SetHardwareTimer(&timer);
 KThread t[4];
 t[0].key=0x1000;t[1].key=0x1000;
 t[2].key=0x2000;t[3].key=0x1000;
 for(auto& x:t){x.arbitration=true;x.BeginWait(k,&q);a.m_tree.insert(x);}
 assert(k.began==4 && k.resumed==0 && a.m_tree.size()==4);
 assert(a.Signal(0x4000,1)==ResultSuccess && k.resumed==0);
 assert(a.Signal(0x1000,1)==ResultSuccess);
 assert(k.resumed==1 && a.m_tree.size()==3);
 assert(t[0].GetState()==ThreadState::Runnable && t[0].m_wait_queue==nullptr);
 assert(t[0].result==ResultSuccess && !t[0].arbitration);
 for(int i=1;i<4;i++)assert(t[i].GetState()==ThreadState::Waiting);
 assert(a.Signal(0x1000,2)==ResultSuccess);
 assert(k.resumed==3 && a.m_tree.size()==1);
 assert(t[2].GetState()==ThreadState::Waiting);
 assert(a.Signal(0x2000,0)==ResultSuccess);
 assert(k.resumed==4 && a.m_tree.size()==0);
 assert(timer.cancelled.size()==4 && k.depth==0);
 for(auto& x:t){
  assert(x.GetState()==ThreadState::Runnable);
  assert(x.m_wait_queue==nullptr && x.result==ResultSuccess && !x.arbitration);
 }
 KThread b[3];b[0].key=0x5000;b[1].key=0x5000;b[2].key=0x6000;
 for(auto& x:b){x.arbitration=true;x.BeginWait(k,&q);a.m_tree.insert(x);}
 assert(a.Signal(0x5000,-1)==ResultSuccess);
 assert(b[0].GetState()==ThreadState::Runnable);
 assert(b[1].GetState()==ThreadState::Runnable);
 assert(b[2].GetState()==ThreadState::Waiting);
 assert(a.m_tree.size()==1);
 assert(a.Signal(0x6000,0)==ResultSuccess);
 assert(a.m_tree.size()==0 && timer.cancelled.size()==7);
 assert(k.began==7 && k.resumed==7 && k.depth==0);
 std::cout<<"ADDRESS_SIGNAL_TO_RUNNABLE_HOST_PASS\n";
}
"""
with tempfile.TemporaryDirectory(prefix="encore-hle-wake-") as td:
    d=Path(td)
    cpp,exe=d/"wake.cpp",d/"wake"
    cpp.write_text(header+methods+footer)
    subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(cpp),"-o",str(exe)],check=True,timeout=40)
    run=subprocess.run([str(exe)],capture_output=True,text=True,check=True,timeout=10)
    print(run.stdout,end="")
print("ADDRESS_WAKE_HOST_ONLY_NO_CONSOLE_OR_REAL_GUEST_JIT_PROOF")
