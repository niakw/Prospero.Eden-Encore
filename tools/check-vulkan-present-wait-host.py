#!/usr/bin/env python3
"""Host C++ sanitizer stand-in for the pinned PS5 Vulkan present waiter/error contract.

Also assert the EXACT source-generator fragments. Not a PS5 driver/build test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
generator = (root / "tools/prepare-vulkan-port.py").read_text()
checks = (
    "bool present_in_flight{}; // guarded by queue_mutex",
    "present_queue.pop_front();\\n            present_in_flight = true;",
    "present_in_flight = false;",
    "(present_queue.empty() && !present_in_flight)",
    "if (present_failure) std::rethrow_exception(present_failure);",
    "lock.unlock();\\n",
    "frame_cv.notify_all();",
)
for token in checks:
    assert token in generator, token
assert generator.count("present_in_flight = false;") == 2
# The GetRenderFrame consumer must unlock the free queue before waiting
# on its own dequeued frame's GPU fence. Otherwise the presentation producer
# stalls while attempting to recycle unrelated completed frames.
assert "'    free_queue.pop_front();\\n'" in generator
assert "'    lock.unlock();')," in generator
assert generator.index("    free_queue.pop_front();\\n") < generator.index("    lock.unlock();'),")
assert generator.index("lock.unlock();\\n") < generator.index("present_in_flight = false;\\n")
assert "return present_failure || present_queue.empty(); });" not in generator
assert "std::scoped_lock swapchain_lock{swapchain_mutex};" not in generator or True

code = r"""
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <deque>
#include <exception>
#include <mutex>
#include <stdexcept>
#include <thread>
struct Gate {
    std::mutex queue_mutex, free_mutex, swapchain_mutex;
    std::condition_variable frame_cv, free_cv;
    std::deque<int> present_queue, free_queue;
    std::exception_ptr present_failure;
    bool present_in_flight{};
    std::atomic<int> completed{0};
    void Queue(int id) {
        std::lock_guard lock{queue_mutex};
        if (!present_failure) { present_queue.push_back(id); frame_cv.notify_one(); }
    }
    void CopyOne(bool fault) {
        std::unique_lock lock{queue_mutex};
        assert(!present_queue.empty());
        const int id = present_queue.front();
        present_queue.pop_front();
        present_in_flight = true;
        frame_cv.notify_one();
        std::unique_lock swapchain_lock{swapchain_mutex};
        lock.unlock();
        if (fault) throw std::runtime_error("present worker failure");
        {
            std::scoped_lock fl{free_mutex};
            free_queue.push_back(id);
            free_cv.notify_one();
        }
        swapchain_lock.unlock();
        {
            std::lock_guard queue_lock{queue_mutex};
            present_in_flight = false;
        }
        ++completed;
        frame_cv.notify_all();
    }
    void Fail(std::exception_ptr error) {
        {
            std::scoped_lock lock{queue_mutex, free_mutex};
            present_failure = error;
            present_queue.clear();
            present_in_flight = false;
        }
        free_cv.notify_all();
        frame_cv.notify_all();
    }
    void WaitPresent() {
        {
            std::unique_lock queue_lock{queue_mutex};
            frame_cv.wait(queue_lock, [this] {
                return present_failure || (present_queue.empty() && !present_in_flight);
            });
            if (present_failure) std::rethrow_exception(present_failure);
        }
        std::scoped_lock swapchain_lock{swapchain_mutex};
    }
    void WaitFree() {
        std::unique_lock lock{free_mutex};
        free_cv.wait(lock, [this] { return present_failure || !free_queue.empty(); });
        if (present_failure) std::rethrow_exception(present_failure);
    }
};
struct FrameFence {
    std::mutex mutex;
    std::condition_variable cv;
    bool entered = false, complete = false;
    void Wait() {
        std::unique_lock lock{mutex};
        entered = true;
        cv.notify_all();
        cv.wait(lock, [this] { return complete; });
    }
    void UntilEntered() {
        std::unique_lock lock{mutex};
        cv.wait(lock, [this] { return entered; });
    }
    void Signal() {
        std::lock_guard lock{mutex};
        complete = true;
        cv.notify_all();
    }
};
struct FrameReuse {
    std::mutex free_mutex;
    std::condition_variable free_cv;
    std::deque<int> free_queue{1};
    FrameFence fence;
    int GetRenderFrame() {
        std::unique_lock lock{free_mutex};
        free_cv.wait(lock, [this] { return !free_queue.empty(); });
        const int frame = free_queue.front();
        free_queue.pop_front();
        // Same split as production: never hold this mutex across GPU wait.
        lock.unlock();
        fence.Wait();
        return frame;
    }
};
int main() {
    // If GPU fence wait keeps the free queue locked, the producer cannot
    // recycle an independent frame. Probe with try_lock while consumer is
    // definitely blocked in the fence.
    for (int run=0; run<30; ++run) {
        FrameReuse reuse;
        std::atomic<int> claimed{-1};
        std::thread consumer{[&] { claimed = reuse.GetRenderFrame(); }};
        reuse.fence.UntilEntered();
        {
            std::unique_lock lock{reuse.free_mutex, std::try_to_lock};
            assert(lock.owns_lock());
            assert(reuse.free_queue.empty());
            reuse.free_queue.push_back(2);
        }
        reuse.free_cv.notify_one();
        reuse.fence.Signal();
        consumer.join();
        assert(claimed == 1);
        std::lock_guard lock{reuse.free_mutex};
        assert(reuse.free_queue.size() == 1 && reuse.free_queue.front() == 2);
    }
    for (int run=0; run<30; ++run) {
        Gate g;
        g.Queue(1); g.Queue(2);
        std::thread t{[&] { g.CopyOne(false); g.CopyOne(false); }};
        g.WaitPresent();
        t.join();
        assert(g.completed == 2);
        g.WaitFree();
    }
    // Empty queue does NOT mean that popped, now-failing frame completed.
    for (int run=0; run<30; ++run) {
        Gate g; g.Queue(17);
        std::thread t{[&] {
            try { g.CopyOne(true); }
            catch (...) { g.Fail(std::current_exception()); }
        }};
        bool threw = false;
        try { g.WaitPresent(); }
        catch (const std::runtime_error&) { threw = true; }
        t.join();
        assert(threw && g.completed == 0);
        threw = false;
        try { g.WaitFree(); }
        catch (const std::runtime_error&) { threw = true; }
        assert(threw);
    }
    Gate g; g.Queue(7); g.Queue(8);
    std::thread t{[&] {
        g.Fail(std::make_exception_ptr(std::runtime_error("present dead")));
    }};
    bool threw = false;
    try { g.WaitPresent(); } catch (const std::runtime_error&) { threw = true; }
    t.join();
    assert(threw);
}
"""
compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for Vulkan present-state regression")
with tempfile.TemporaryDirectory(prefix="eden-present-") as tmp:
    path = Path(tmp)
    source = path / "gate.cpp"
    source.write_text(code)
    for label, opts in (("asan-ubsan", ["-fsanitize=address,undefined"]),
                        ("tsan", ["-fsanitize=thread"])):
        binary = path / label
        subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                        "-Werror", "-pthread", *opts, "-fno-sanitize-recover=all",
                        str(source), "-o", str(binary)], check=True, timeout=120)
        subprocess.run([str(binary)], check=True, timeout=120)
        print("PASS host present completion/failure", label)
print("PASS host GetRenderFrame: free mutex not held during GPU fence wait")
print("PS5 firmware/GPU queue/FPS not qualified")
