#!/usr/bin/env python3
"""Host ASan/UBSan: source-extracted Vulkan worker fatal-exit and queue drain.

Checks the actual maintained constructor lambda, WorkerThread body and
WaitWorker in PS5_NATIVE and non-native configurations. No console timings.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
CI=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
def extract(begin, end):
    assert SRC.count(begin)==1, (begin, SRC.count(begin))
    a=SRC.index(begin)
    return SRC[a:SRC.index(end,a)].rstrip()
CTOR=extract("    worker_thread = std::jthread([this](std::stop_token token) {", "\n}\n\nScheduler::~Scheduler")
WAIT=extract("void Scheduler::WaitWorker() {", "\nvoid Scheduler::DispatchWork()")
WORKER=extract("void Scheduler::WorkerThread(std::stop_token stop_token) {", "\nvoid Scheduler::AllocateWorkerCommandBuffer()")
assert "RecordGpuFailure(std::current_exception())" in CTOR
assert "RecordGpuFailure(std::current_exception())" in WORKER
assert "PeekGpuFailure()" in WAIT
assert WAIT.count("--queue_drain_waiters;")==1
assert "event_cv.notify_all();" in CTOR and "event_cv.notify_all();" in WORKER
assert "try {" in WORKER and "catch (...)" in WORKER
assert WORKER.index("::Eden::RecordGpuFailure(")<WORKER.index("event_cv.notify_all();",WORKER.index("::Eden::RecordGpuFailure("))
assert "Publish failure before releasing execution_mutex" in SRC
assert "Background setup failures must also reach native GPU observers." in GEN
assert "python3 -B tools/check-vulkan-worker-fatal-drain-host.py" in CI

CPP=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <stop_token>
#include <thread>
#include <utility>
#include <vector>
#ifdef PS5_NATIVE
#include "gpu_failure.h"
namespace Eden::Performance {
inline void ProbeSchedulerOnce(const char*) {}
}
#endif
namespace Common {
enum class ThreadPriority { Critical };
inline void SetCurrentThreadName(const char*) {}
inline void SetCurrentThreadPriority(ThreadPriority) {}
inline void SetCurrentThreadToPerformanceCores() {}
}
struct CommandChunk {
    enum Kind { Ordinary, ThrowExecute, ThrowAllocate };
    Kind kind=Ordinary;
    std::atomic<unsigned>* completed=nullptr;
    bool HasSubmit() const { return kind==ThrowAllocate; }
    void ExecuteAll(int,int) {
        if(kind==ThrowExecute) throw std::runtime_error("Vulkan command callback");
        if(completed) completed->fetch_add(1);
    }
};
class Scheduler {
public:
    std::queue<std::unique_ptr<CommandChunk>> work_queue;
    std::vector<std::unique_ptr<CommandChunk>> chunk_reserve;
    std::mutex execution_mutex, reserve_mutex, queue_mutex;
    std::condition_variable_any event_cv;
    unsigned queue_drain_waiters{};
    std::jthread worker_thread;
    std::atomic<unsigned> completed{0};
    int current_cmdbuf=0,current_upload_cmdbuf=0;
    Scheduler() {
INJECT_CTOR
    }
    ~Scheduler() {
        worker_thread.request_stop();
        event_cv.notify_all();
        if(worker_thread.joinable()) worker_thread.join();
    }
    void DispatchWork() {}
    void AllocateWorkerCommandBuffer() {
        throw std::runtime_error("Vulkan allocation");
    }
    void Push(CommandChunk::Kind kind) {
        auto command=std::make_unique<CommandChunk>();
        command->kind=kind;
        command->completed=&completed;
        {
            std::scoped_lock lock{queue_mutex};
            work_queue.push(std::move(command));
        }
        event_cv.notify_all();
    }
    void WaitWorker();
    void WorkerThread(std::stop_token stop_token);
};
INJECT_WAIT
INJECT_WORKER
int main() {
    using namespace std::chrono_literals;
#ifdef PS5_NATIVE
    Eden::ResetGpuFailureForTitle();
#endif
    {
        Scheduler scheduler;
        scheduler.Push(CommandChunk::Ordinary);
        auto future=std::async(std::launch::async,[&] { scheduler.WaitWorker(); });
        assert(future.wait_for(4s)==std::future_status::ready);
        future.get();
        assert(scheduler.completed.load()==1);
        assert(scheduler.queue_drain_waiters==0);
    }
#ifdef PS5_NATIVE
    {
        Scheduler scheduler;
        // Leave another command queued behind the failing one. Without the
        // fail-aware drain predicate, WaitWorker would never complete.
        scheduler.Push(CommandChunk::ThrowExecute);
        scheduler.Push(CommandChunk::Ordinary);
        auto future=std::async(std::launch::async,[&] { scheduler.WaitWorker(); });
        assert(future.wait_for(4s)==std::future_status::ready);
        bool caught=false;
        try { future.get(); } catch(const std::runtime_error& e) {
            caught=std::string(e.what())=="Vulkan command callback";
        }
        assert(caught && scheduler.queue_drain_waiters==0);
        assert(scheduler.completed.load()==0 && Eden::PeekGpuFailure());
        assert(Eden::TakeGpuFailure());
        assert(Eden::PeekGpuFailure());
    }
    Eden::ResetGpuFailureForTitle();
    {
        Scheduler scheduler;
        scheduler.Push(CommandChunk::ThrowAllocate);
        auto future=std::async(std::launch::async,[&] { scheduler.WaitWorker(); });
        assert(future.wait_for(4s)==std::future_status::ready);
        bool caught=false;
        try { future.get(); } catch(const std::runtime_error& e) {
            caught=std::string(e.what())=="Vulkan allocation";
        }
        assert(caught && scheduler.queue_drain_waiters==0);
    }
    Eden::ResetGpuFailureForTitle();
#endif
}
""".replace("INJECT_CTOR",CTOR).replace("INJECT_WAIT",WAIT).replace("INJECT_WORKER",WORKER)
compiler=os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-vulkan-worker-fatal-") as tmp:
    d=Path(tmp)
    src=d/"worker.cpp"
    src.write_text(CPP)
    for name,flags in (("host",[]),("native",["-DPS5_NATIVE=1"])):
        exe=d/name
        subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra",
            "-pthread","-fsanitize=address,undefined","-fno-sanitize-recover=all",
            "-I",str(ROOT/"headless"),*flags,str(src),"-o",str(exe)],
            check=True,capture_output=True,text=True,timeout=70)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        assert result.returncode==0,(name,result.stdout[-900:],result.stderr[-1600:])
print("ENCORE_VULKAN_WORKER_FATAL_DRAIN_PASS source_extracted=3 host_normal=1 native_failure=2 waiters_released=1 sanitizer=1")
