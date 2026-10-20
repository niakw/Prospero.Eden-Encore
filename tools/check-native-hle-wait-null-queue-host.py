#!/usr/bin/env python3
"""Compile exact native HLE wake/cancel methods under ASan/UBSan.

A missing wait queue is an invariant violation, but should never become an
unchecked null dereference. Existing EndWait already implements this contract.
This covers defensive CPU-host behavior, not real title liveness.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ACT=(ROOT/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.cpp").read_text()
PIN=(ROOT/"vendor/sources/eden/src/core/hle/kernel/k_thread.cpp").read_text()
FLOW=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
ORACLE=(ROOT/"tools/verify/hle/check-hle-overlay-layout.py").read_text()
assert "python3 -B tools/check-native-hle-wait-null-queue-host.py" in FLOW
assert "python3 -B tools/check-native-hle-wait-null-queue-host.py" in FAST
assert "notify_before" in ORACLE and "cancel_before" in ORACLE
def get(s,method):
    marker="    void KThread::"+method+"("
    assert s.count(marker)==1
    return s[s.index(marker):].split("\n    }",1)[0]+"\n    }"
methods=["NotifyAvailable","CancelWait"]
for m in methods:
    assert "if (m_wait_queue == nullptr)" in get(ACT,m)
    assert "if (m_wait_queue == nullptr)" not in get(PIN,m)
    assert "ASSERT_MSG(false" in get(ACT,m)
cpp=r"""
#include <cassert>
#include <cstdio>
struct KernelCore {};
struct KSynchronizationObject {};
using Result=int;
enum class ThreadState { Runnable, Waiting };
int diagnostic_hits=0;
#define ASSERT_MSG(cond, reason) do { if(!(cond)) ++diagnostic_hits; } while (false)
struct KScopedSchedulerLock { explicit KScopedSchedulerLock(KernelCore&) {} };
class KThread;
struct KThreadQueue {
    int wake_count=0,cancel_count=0;
    void NotifyAvailable(KernelCore&,KThread*,KSynchronizationObject*,Result){++wake_count;}
    void CancelWait(KernelCore&,KThread*,Result,bool){++cancel_count;}
};
class KThread {
public:
    ThreadState state=ThreadState::Waiting;
    KThreadQueue* m_wait_queue=nullptr;
    ThreadState GetState() const {return state;}
    void NotifyAvailable(KernelCore&,KSynchronizationObject*,Result);
    void CancelWait(KernelCore&,Result,bool);
};
INJECT_NOTIFY
INJECT_CANCEL
int main() {
    KernelCore kernel;
    KSynchronizationObject signal;
    KThread thread;
    // Both should report the broken invariant instead of dereferencing null.
    thread.NotifyAvailable(kernel,&signal,0);
    thread.CancelWait(kernel,0,true);
    assert(diagnostic_hits==2);
    KThreadQueue queue;
    thread.m_wait_queue=&queue;
    thread.NotifyAvailable(kernel,&signal,0);
    thread.CancelWait(kernel,0,true);
    assert(queue.wake_count==1 && queue.cancel_count==1);
    assert(diagnostic_hits==2);
    thread.state=ThreadState::Runnable;
    thread.m_wait_queue=nullptr;
    thread.NotifyAvailable(kernel,&signal,0);
    thread.CancelWait(kernel,0,true);
    assert(diagnostic_hits==2);
    std::puts("HLE_NULL_QUEUE_WAKE_CANCEL_PASS");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler needed"
with tempfile.TemporaryDirectory(prefix="encore-hle-null-queue-") as td:
    path=Path(td)
    for label,src,positive in (("pinned",PIN,False),("native",ACT,True)):
        contents=cpp.replace("INJECT_NOTIFY",get(src,"NotifyAvailable"))
        contents=contents.replace("INJECT_CANCEL",get(src,"CancelWait"))
        c=path/(label+".cpp");exe=path/label
        c.write_text(contents)
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        str(c),"-o",str(exe)],check=True,timeout=90)
        proc=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        if positive:
            assert proc.returncode==0,proc.stderr[-1400:]
        else:
            assert proc.returncode!=0,"Pinned source unexpectedly handled invalid queue"
print("HLE_NULL_QUEUE_HOST_PASS; game progression unqualified")
