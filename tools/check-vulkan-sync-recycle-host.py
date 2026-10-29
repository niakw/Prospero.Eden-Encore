#!/usr/bin/env python3
"""Run real source-extracted synchronous/async Vulkan Present and GetRenderFrame.

A recycled frame must be pushed under free_mutex and wake consumers only
after it is available. The async path and failed copy must remain unchanged.
Host ASan/UBSan, not a native-console performance experiment.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
CI=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
start=SOURCE.index("Frame* PresentManager::GetRenderFrame() {")
end=SOURCE.index("\nsize_t PresentManager::MaxExtraFrames() const {", start)
METHODS=SOURCE[start:end]
assert METHODS.count("void PresentManager::Present(Frame* frame) {")==1
sync=METHODS.split("    } else {\n        scheduler.WaitWorker();",1)[1]
assert sync.index("CopyToSwapchain(frame);") < sync.index("std::scoped_lock lock{free_mutex};")
assert sync.index("free_queue.push_back(frame);") < sync.index("free_cv.notify_one();")
assert "std::scoped_lock lock{free_mutex};" in sync
assert "free_cv.wait(lock, [this] { return present_failure || !free_queue.empty(); });" in METHODS
assert "std::unique_lock lock{queue_mutex};" in METHODS
assert "Synchronous presentation must publish its recycled frame" in GEN
assert "python3 -B tools/check-vulkan-sync-recycle-host.py" in CI

CPP=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <exception>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>
namespace vk { using CommandBuffer=int; }
namespace Eden::Performance {
inline constexpr int gpu_present_wait=0;
inline constexpr int gpu_present_free_wait=1;
inline constexpr int gpu_present_fence_wait=2;
struct DiagnosticTimer { explicit DiagnosticTimer(int) {} };
}
struct Frame {
    struct Fence {
        unsigned waits=0, resets=0;
        void Wait() { ++waits; }
        void Reset() { ++resets; }
    } present_done;
};
struct CheckedMutex {
    std::mutex mutex;
    std::atomic<bool> locked{false};
    std::atomic<unsigned> locks{0};
    void lock() {
        mutex.lock();
        locked.store(true);
        locks.fetch_add(1);
    }
    void unlock() {
        locked.store(false);
        mutex.unlock();
    }
};
struct CheckedFrames {
    CheckedMutex* gate=nullptr;
    std::deque<Frame*> items;
    bool empty() const { return items.empty(); }
    Frame* front() { assert(gate->locked.load()); return items.front(); }
    void pop_front() { assert(gate->locked.load()); items.pop_front(); }
    void push_back(Frame* frame) {
        assert(gate->locked.load() && "free_queue writer must own free_mutex");
        items.push_back(frame);
    }
};
struct FreeCV {
    std::condition_variable_any condition;
    std::atomic<bool> entered{false};
    std::atomic<unsigned> notifications{0};
    template <class Lock, class Predicate> void wait(Lock& lock, Predicate&& pred) {
        entered.store(true);
        condition.wait(lock, std::forward<Predicate>(pred));
    }
    void notify_one() { ++notifications; condition.notify_one(); }
};
struct PresentReadyCV {
    std::atomic<unsigned> notifications{0};
    void notify_one() { notifications.fetch_add(1); }
};
struct Scheduler {
    unsigned drains=0;
    std::vector<std::function<void(vk::CommandBuffer)>> queued;
    void WaitWorker() { ++drains; }
    template <class F> void Record(F&& f) { queued.emplace_back(std::forward<F>(f)); }
};
struct PresentManager {
    explicit PresentManager(bool async)
        : use_present_thread(async) { free_queue.gate=&free_mutex; }
    bool use_present_thread=false;
    bool throw_copy=false;
    unsigned copies=0;
    CheckedMutex free_mutex;
    FreeCV free_cv;
    CheckedFrames free_queue;
    std::mutex queue_mutex;
    std::deque<Frame*> present_queue;
    std::condition_variable frame_cv;
    PresentReadyCV present_ready_cv;
    std::exception_ptr present_failure;
    Scheduler scheduler;
    void CopyToSwapchain(Frame*) {
        assert(!free_mutex.locked.load() && "no free mutex during GPU copy");
        ++copies;
        if (throw_copy) throw std::runtime_error("native copy failed");
    }
    Frame* GetRenderFrame();
    void Present(Frame*);
};
INJECT_METHODS
int main() {
    {
        PresentManager p(false);
        Frame frame;
        std::atomic<Frame*> received{nullptr};
        std::thread waiter([&] { received.store(p.GetRenderFrame()); });
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(4);
        // The waiter publishes entered just before condition_variable_any
        // releases free_mutex. Observe both events, not just the flag.
        while ((!p.free_cv.entered.load() || p.free_mutex.locked.load()) &&
               std::chrono::steady_clock::now()<deadline)
            std::this_thread::yield();
        assert(p.free_cv.entered.load() && !p.free_mutex.locked.load());
        p.Present(&frame);
        waiter.join();
        assert(received.load()==&frame && frame.present_done.waits==1);
        assert(frame.present_done.resets==1 && p.scheduler.drains==1);
        assert(p.copies==1 && p.free_cv.notifications.load()==1);
        assert(p.present_ready_cv.notifications.load()==0);
        assert(p.free_mutex.locks.load()>=2 && p.free_queue.empty());
    }
    {
        PresentManager p(false);
        Frame frame;
        p.throw_copy=true;
        bool threw=false;
        try { p.Present(&frame); } catch (const std::runtime_error&) { threw=true; }
        assert(threw && p.scheduler.drains==1 && p.copies==1);
        assert(p.free_queue.empty() && p.free_cv.notifications.load()==0);
    }
    {
        PresentManager p(true);
        Frame frame;
        p.Present(&frame);
        assert(p.scheduler.drains==0 && p.copies==0);
        assert(p.free_queue.empty() && p.scheduler.queued.size()==1);
        p.scheduler.queued.front()(0);
        assert(p.present_queue.size()==1 && p.present_queue.front()==&frame);
        assert(p.free_cv.notifications.load()==0);
        assert(p.present_ready_cv.notifications.load()==1);
    }
}
""".replace("INJECT_METHODS",METHODS)
compiler=os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "A host C++20 compiler is required"
with tempfile.TemporaryDirectory(prefix="encore-sync-present-recycle-") as tmp:
    out=Path(tmp)
    src=out/"witness.cpp"
    exe=out/"witness"
    src.write_text(CPP)
    compile_result=subprocess.run(
        [compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
         "-pthread","-fsanitize=address,undefined",
         "-fno-sanitize-recover=all",str(src),"-o",str(exe)],
        capture_output=True,text=True,timeout=80)
    assert compile_result.returncode==0, (
        compile_result.returncode,compile_result.stderr[-4000:])
    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,(result.returncode,result.stdout[-1000:],result.stderr[-2000:])
print("ENCORE_SYNC_PRESENT_RECYCLE_PASS source_extracted=1 mutex=1 wake=1 copy_failure=1 async_unchanged=1 asan_ubsan=1")
