#!/usr/bin/env python3
"""Real-source host witness for IPC enqueue and kernel wait-queue completion.

Extracts the current KServerSession::OnRequest and KThreadQueue::EndWait /
CancelWait definitions, compiles them as C++20 under ASan/UBSan, and tests
error, synchronous, asynchronous and timer paths. This is NOT an emulated
guest CPU run, a native console build, or proof that FC27 freezes are fixed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "vendor/sources/eden/src/core/hle/kernel/k_server_session.cpp").read_text()
CLIENT = (ROOT / "vendor/sources/eden/src/core/hle/kernel/k_client_session.cpp").read_text()
QUEUE = (ROOT / "vendor/sources/eden/src/core/hle/kernel/k_thread_queue.cpp").read_text()
FAST = (ROOT / ".github/workflows/encore-core-fast-gate.yml").read_text()
FULL = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
INVOCATION = "python3 -B tools/check-native-ipc-wake-chain-host.py"
assert INVOCATION in FAST and INVOCATION in FULL

def extract(text: str, signature: str) -> str:
    marker = signature + " {"
    assert text.count(marker) == 1, (signature, "source drift")
    start = text.index(marker)
    brace = start + len(signature) + 1
    depth = 0
    for pos in range(brace, len(text)):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                return text[start:pos + 1]
    raise AssertionError("unbalanced extracted function " + signature)

server = extract(SERVER, "Result KServerSession::OnRequest(KernelCore& kernel, KSessionRequest* request)")
end = extract(QUEUE, "void KThreadQueue::EndWait(KernelCore& kernel, KThread* waiting_thread, Result wait_result)")
cancel = extract(QUEUE, "void KThreadQueue::CancelWait(KernelCore& kernel, KThread* waiting_thread, Result wait_result, bool cancel_timer_task)")
# These are source/edge invariants; the C++ fixture exercises the real bodies
# in addition to asserting that client-side request ownership is preserved.
sync = extract(CLIENT, "Result KClientSession::SendSyncRequest(KernelCore& kernel, uintptr_t address, size_t size)")
async_req = extract(CLIENT, "Result KClientSession::SendAsyncRequest(KernelCore& kernel, KEvent* event, uintptr_t address, size_t size)")
for src in (sync, async_req):
    assert src.index("request->Initialize(") < src.index("m_parent->OnRequest(kernel, request)")
    assert "request->Close(kernel)" in src and "KSessionRequest::Create(kernel)" in src
assert "request->Initialize(kernel, nullptr, address, size)" in sync
assert "request->Initialize(kernel, event, address, size)" in async_req
assert server.index("request->Open(kernel)") < server.index("m_request_list.push_back(*request)")
assert server.index("this->NotifyAvailable(kernel)") < server.index("GetCurrentThread(kernel).BeginWait")
assert end.index("SetWaitResult(") < end.index("SetState(") < end.index("ClearWaitQueue()")
assert cancel.index("SetWaitResult(") < cancel.index("SetState(") < cancel.index("ClearWaitQueue()")

CPP = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <utility>
#include <vector>
using std::string;
using std::vector;
enum Result {
    ResultSuccess=0, ResultSessionClosed=1,
    ResultTerminationRequested=2, ResultTimedOut=3,
    ResultInvalidState=4, ResultCancelled=5
};
#define R_UNLESS(test, err) do { if (!(test)) return err; } while (false)
#define R_SUCCEED_IF(test) do { if (test) return ResultSuccess; } while (false)
struct KThread;
struct KernelCore {
    KThread* thread{};
    int lock_depth{};
    vector<string> trace;
};
struct KScopedSchedulerLock {
    KernelCore& kernel;
    explicit KScopedSchedulerLock(KernelCore& k):kernel(k){++kernel.lock_depth;}
    ~KScopedSchedulerLock(){--kernel.lock_depth;}
};
struct KHardwareTimer {
    KernelCore& kernel;
    unsigned calls{};
    void CancelTask(KThread*) {++calls;kernel.trace.push_back("cancel_timer");}
};
enum class ThreadState {Waiting, Runnable};
enum class ThreadWaitReasonForDebugging { IPC };
struct KThreadQueue;
struct KThread {
    KernelCore& kernel;
    bool terminating{};
    bool wait_queue_active{};
    ThreadState state=ThreadState::Waiting;
    Result wait_result=ResultTimedOut;
    Result desired_result=ResultSuccess;
    unsigned begin_count{};
    explicit KThread(KernelCore& k):kernel(k){k.thread=this;}
    bool IsTerminationRequested() const { return terminating; }
    void SetWaitReasonForDebugging(ThreadWaitReasonForDebugging) {
        kernel.trace.push_back("reason");
    }
    void BeginWait(KernelCore&, KThreadQueue*);
    void SetWaitResult(Result r) { wait_result=r; kernel.trace.push_back("result"); }
    void SetState(KernelCore&, ThreadState s) {
        assert(kernel.lock_depth>0);
        state=s;
        kernel.trace.push_back("runnable");
    }
    void ClearWaitQueue() {wait_queue_active=false;kernel.trace.push_back("clear");}
    Result GetWaitResult() const {return wait_result;}
};
struct KThreadQueue {
    KHardwareTimer* m_hardware_timer{};
    explicit KThreadQueue(KernelCore&) {}
    void EndWait(KernelCore&, KThread*, Result);
    void CancelWait(KernelCore&, KThread*, Result, bool);
};
using ThreadQueueImplForKServerSessionRequest = KThreadQueue;
void KThread::BeginWait(KernelCore& k, KThreadQueue* queue) {
    assert(k.lock_depth>0);
    wait_queue_active=true;
    ++begin_count;
    k.trace.push_back("begin_wait");
    // Synchronous completion double, NOT a guest scheduler or fiber.
    queue->EndWait(k, this, desired_result);
}
struct KSessionRequest {
    KernelCore& kernel;
    bool has_event{};
    unsigned opens{};
    explicit KSessionRequest(KernelCore& k, bool event=false):kernel(k),has_event(event){}
    void* GetEvent() const {return has_event?reinterpret_cast<void*>(1):nullptr;}
    void Open(KernelCore& k) {assert(&k==&kernel);++opens;k.trace.push_back("open");}
};
struct KSessionParent {
    bool server_closed{};
    bool IsServerClosed() const {return server_closed;}
};
struct RequestList {
    KernelCore& kernel;
    vector<KSessionRequest*> elements;
    explicit RequestList(KernelCore& k):kernel(k){}
    bool empty() const {return elements.empty();}
    void push_back(KSessionRequest& req) {
        elements.push_back(&req);
        kernel.trace.push_back("push");
    }
};
struct KServerSession {
    KernelCore& owner;
    KSessionParent* m_parent{};
    RequestList m_request_list;
    unsigned notifications{};
    explicit KServerSession(KernelCore& k,KSessionParent& p):
        owner(k),m_parent(&p),m_request_list(k){}
    void NotifyAvailable(KernelCore& k) {
        assert(k.lock_depth>0);
        ++notifications;
        k.trace.push_back("notify");
    }
    Result OnRequest(KernelCore&, KSessionRequest*);
};
KThread& GetCurrentThread(KernelCore& k) {
    assert(k.thread);
    return *k.thread;
}
INJECT
static void check_trace(const KernelCore& k, const vector<string>& expected) {
    assert(k.trace==expected);
    assert(k.lock_depth==0);
}
int main() {
    unsigned checks=0;
    for(int iter=0;iter<24;++iter) {
      {
        KernelCore k; KThread thread(k); KSessionParent parent;
        KServerSession server(k,parent); KSessionRequest req(k);
        thread.desired_result=ResultCancelled;
        const Result result=server.OnRequest(k,&req);
        assert(result==ResultCancelled && thread.begin_count==1);
        assert(thread.state==ThreadState::Runnable && !thread.wait_queue_active);
        assert(server.notifications==1 && req.opens==1);
        assert(server.m_request_list.elements.size()==1);
        check_trace(k,{"open","push","notify","reason","begin_wait","result","runnable","clear"});
        ++checks;
      }
      {
        KernelCore k;KThread thread(k);KSessionParent parent;
        KServerSession server(k,parent);KSessionRequest req(k,true);
        assert(server.OnRequest(k,&req)==ResultSuccess);
        assert(thread.begin_count==0 && server.notifications==1 && req.opens==1);
        check_trace(k,{"open","push","notify"});
        ++checks;
      }
      {
        KernelCore k;KThread thread(k);KSessionParent parent;
        KServerSession server(k,parent);
        KSessionRequest first(k,true),second(k,true);
        assert(server.OnRequest(k,&first)==ResultSuccess);
        k.trace.clear();
        assert(server.OnRequest(k,&second)==ResultSuccess);
        assert(server.notifications==1 && second.opens==1);
        check_trace(k,{"open","push"});
        ++checks;
      }
      {
        KernelCore k;KThread thread(k);KSessionParent parent;
        parent.server_closed=true;
        KServerSession server(k,parent);KSessionRequest req(k);
        assert(server.OnRequest(k,&req)==ResultSessionClosed);
        assert(req.opens==0 && server.notifications==0 && thread.begin_count==0);
        check_trace(k,{});
        ++checks;
      }
      {
        KernelCore k;KThread thread(k);KSessionParent parent;
        thread.terminating=true;
        KServerSession server(k,parent);KSessionRequest req(k);
        assert(server.OnRequest(k,&req)==ResultTerminationRequested);
        assert(req.opens==0 && server.notifications==0 && thread.begin_count==0);
        check_trace(k,{});
        ++checks;
      }
      {
        KernelCore k;KThread thread(k);KThreadQueue queue(k);
        KHardwareTimer timer{k};queue.m_hardware_timer=&timer;
        KScopedSchedulerLock lock(k);
        thread.wait_queue_active=true;
        queue.EndWait(k,&thread,ResultSuccess);
        assert(thread.wait_result==ResultSuccess && !thread.wait_queue_active);
        assert(timer.calls==1 && thread.state==ThreadState::Runnable);
        assert(k.trace==(vector<string>{"result","runnable","clear","cancel_timer"}));
        ++checks;
      }
      for(bool cancel_task: {false,true}) {
        KernelCore k;KThread thread(k);KThreadQueue queue(k);
        KHardwareTimer timer{k};queue.m_hardware_timer=&timer;
        {
            KScopedSchedulerLock lock(k);
            thread.wait_queue_active=true;
            queue.CancelWait(k,&thread,ResultCancelled,cancel_task);
        }
        assert(thread.wait_result==ResultCancelled && !thread.wait_queue_active);
        assert(timer.calls==static_cast<unsigned>(cancel_task));
        assert(k.trace==(cancel_task?
           vector<string>{"result","runnable","clear","cancel_timer"}:
           vector<string>{"result","runnable","clear"}));
        ++checks;
      }
    }
    assert(checks==192);
    std::printf("ENCORE_IPC_WAKE_CHAIN_HOST_PASS cases=%u\n", checks);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler unavailable"
with tempfile.TemporaryDirectory(prefix="encore-ipc-wake-") as tmp:
    src=Path(tmp)/"ipc_wake.cpp"
    exe=Path(tmp)/"ipc_wake"
    src.write_text(CPP.replace("INJECT","\n\n".join((end,cancel,server))))
    subprocess.run(
        [compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
         "-fsanitize=address,undefined","-fno-sanitize-recover=all",
         str(src),"-o",str(exe)],
        check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("NATIVE_IPC_WAKE_CHAIN_HOST_PASS; guest CPU/fiber progress and PS5 freezes unmeasured")
