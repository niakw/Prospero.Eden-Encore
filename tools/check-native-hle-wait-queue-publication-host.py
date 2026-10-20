#!/usr/bin/env python3
"""Source-extracted host proof: KThread wait queue exists at the state transition.

The scheduler can inspect waiting thread state while the kernel lock is held.
This test intentionally instruments SetState() to reject a transient waiting
state without a queue; the original pinned implementation is the negative
control. Hardware guest progress and title freezes remain unmeasured.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
active=(ROOT/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.cpp").read_text()
pinned=(ROOT/"vendor/sources/eden/src/core/hle/kernel/k_thread.cpp").read_text()
ci=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
selector=(ROOT/"vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
assert "python3 -B tools/check-native-hle-wait-queue-publication-host.py" in ci
assert '"hle/kernel/k_thread.cpp" "core/hle/kernel/k_thread.cpp"' in selector
mark="    void KThread::BeginWait(KernelCore& kernel, KThreadQueue* queue) {"
def extract(text):
    assert text.count(mark)==1
    return text[text.index(mark):].split("\n    }",1)[0]+"\n    }"
native=extract(active)
baseline=extract(pinned)
assert native.index("m_wait_queue = queue;") < native.index("this->SetState(kernel, ThreadState::Waiting);")
assert baseline.index("m_wait_queue = queue;") > baseline.index("this->SetState(kernel, ThreadState::Waiting);")
cpp=r"""
#include <cassert>
#include <cstdio>
struct KernelCore {};
struct KThreadQueue {};
enum class ThreadState { Runnable, Waiting };
class KThread {
public:
    ThreadState state=ThreadState::Runnable;
    KThreadQueue* m_wait_queue=nullptr;
    unsigned state_observations=0;
    void SetState(KernelCore&,ThreadState next) {
        if(next==ThreadState::Waiting) {
            ++state_observations;
            assert(m_wait_queue!=nullptr &&
                   "Cannot enter Waiting before publishing the wake queue");
        }
        state=next;
    }
    void BeginWait(KernelCore&,KThreadQueue*);
};
INJECT
int main() {
    KernelCore kernel;
    KThreadQueue queue;
    KThread thread;
    thread.BeginWait(kernel,&queue);
    assert(thread.state==ThreadState::Waiting);
    assert(thread.m_wait_queue==&queue);
    assert(thread.state_observations==1);
    std::puts("ENCORE_HLE_QUEUE_PUBLICATION_PASS");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-hle-wait-queue-") as temp:
    folder=Path(temp)
    for name,method,expect_pass in (("pinned",baseline,False),("active",native,True)):
        path=folder/(name+".cpp")
        exe=folder/name
        path.write_text(cpp.replace("INJECT",method))
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        str(path),"-o",str(exe)],check=True,timeout=90)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        if expect_pass:
            assert result.returncode==0,(name,result.stdout,result.stderr[-1300:])
        else:
            assert result.returncode!=0,"Pinned source did not reproduce the transient"
print("HLE_WAIT_QUEUE_PUBLICATION_HOST_PASS; PS5 wake scheduling unverified")
