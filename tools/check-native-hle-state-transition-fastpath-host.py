#!/usr/bin/env python3
"""Compile real KThread::SetState, compare atomic state writes and scheduler callbacks.

Pinned and active sources run the same state×suspension matrix under
ASan/UBSan. This witnesses a local no-op fast path, not guest liveness.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ACTIVE=(ROOT/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.cpp").read_text()
PIN=(ROOT/"vendor/sources/eden/src/core/hle/kernel/k_thread.cpp").read_text()
CMAKE=(ROOT/"vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
ORACLE=(ROOT/"tools/verify/hle/check-hle-overlay-layout.py").read_text()
assert '"hle/kernel/k_thread.cpp" "core/hle/kernel/k_thread.cpp"' in CMAKE
assert "python3 -B tools/check-native-hle-state-transition-fastpath-host.py" in FAST
assert "python3 -B tools/check-native-hle-state-transition-fastpath-host.py" in FULL
assert "state_before" in ORACLE and "state_after" in ORACLE
marker="    void KThread::SetState(KernelCore& kernel, ThreadState state) {"
def extract(source):
    assert source.count(marker)==1
    return source[source.index(marker):].split("\n    }",1)[0]+"\n    }"
old=extract(PIN)
new=extract(ACTIVE)
assert old.count("m_thread_state.load(std::memory_order_relaxed)")==2
assert new.count("m_thread_state.load(std::memory_order_relaxed)")==1
assert "const ThreadState next_state" in new
assert new.count("KScheduler::OnThreadStateChanged(kernel, this, old_state);")==1
cpp=r"""
#include <atomic>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
using u16=std::uint16_t;
enum class ThreadState:u16{
 Initialized=0,Waiting=1,Runnable=2,Terminated=3,Mask=15,
 ProcessSuspended=16,ThreadSuspended=32,DebugSuspended=64
};
constexpr ThreadState operator&(ThreadState a,ThreadState b){
 return static_cast<ThreadState>(static_cast<u16>(a)&static_cast<u16>(b));
}
constexpr ThreadState operator|(ThreadState a,ThreadState b){
 return static_cast<ThreadState>(static_cast<u16>(a)|static_cast<u16>(b));
}
constexpr ThreadState operator~(ThreadState a){
 return static_cast<ThreadState>(~static_cast<u16>(a));
}
struct KernelCore{int locks=0;};
struct KScopedSchedulerLock{
 KernelCore& kernel;
 explicit KScopedSchedulerLock(KernelCore& k):kernel(k){++k.locks;}
 ~KScopedSchedulerLock(){--kernel.locks;}
};
struct KThread;
struct KScheduler{static void OnThreadStateChanged(KernelCore&,KThread*,ThreadState);};
struct TrackingAtomic{
 ThreadState value{};
 mutable int loads=0;
 int stores=0;
 ThreadState load(std::memory_order)const{++loads;return value;}
 void store(ThreadState value_,std::memory_order){++stores;value=value_;}
};
struct KThread{
 TrackingAtomic m_thread_state{};
 int debug_clears=0,notifications=0;
 ThreadState previous{};
 void SetWaitReasonForDebugging(ThreadState){++debug_clears;}
 void SetState(KernelCore&,ThreadState);
};
void KScheduler::OnThreadStateChanged(KernelCore& kernel,KThread* thread,ThreadState old){
 assert(kernel.locks>0);
 ++thread->notifications;
 thread->previous=old;
}
INJECT
int main(){
 KernelCore kernel;
 unsigned checked=0,unmodified=0,changed=0;
 for(u16 flags:u16{0},flags_placeholder){(void)flags;}
 for(u16 flags:std::array<u16,5>{0,16,32,48,112}){
  for(u16 from=0;from<4;++from){
   for(u16 to=0;to<4;++to){
    KThread thread;
    auto old=static_cast<ThreadState>(flags|from);
    auto state=static_cast<ThreadState>(flags|to);
    thread.m_thread_state.value=old;
    thread.SetState(kernel,state);
    auto expected=static_cast<ThreadState>((old & ~ThreadState::Mask)|(state & ThreadState::Mask));
    assert(thread.m_thread_state.value==expected);
    assert(thread.notifications==(expected!=old));
    assert(thread.debug_clears==1);
    assert(kernel.locks==0);
    if(expected!=old) {
       ++changed;
       assert(thread.previous==old);
       assert(thread.m_thread_state.stores==1);
    } else {
       ++unmodified;
       assert(thread.m_thread_state.stores==NOOP_STORES);
    }
    assert(thread.m_thread_state.loads==EXPECTED_LOADS);
    ++checked;
   }
  }
 }
 assert(checked==80 && unmodified==20 && changed==60);
 std::printf("ENCORE_HLE_SETSTATE_PASS cases=%u noop=%u transitions=%u\\n",checked,unmodified,changed);
}
"""
# Remove no-op placeholder used to keep the fixture templated and small.
cpp=cpp.replace(" for(u16 flags:u16{0},flags_placeholder){(void)flags;}\n","")
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-hle-state-") as tmp:
    folder=Path(tmp)
    for name,method,loads,no_op_stores in (
        ("pinned",old,2,1),("native",new,1,0)
    ):
        p=folder/(name+".cpp")
        exe=folder/name
        body=cpp.replace("INJECT",method)
        body=body.replace("EXPECTED_LOADS",str(loads)).replace("NOOP_STORES",str(no_op_stores))
        p.write_text(body)
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        str(p),"-o",str(exe)],check=True,timeout=90)
        subprocess.run([str(exe)],check=True,timeout=30)
print("NATIVE_HLE_STATE_FASTPATH_HOST_PASS; guest_frametimes=unmeasured")
