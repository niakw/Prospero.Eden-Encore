#!/usr/bin/env python3
"""Test actual Vulkan PresentManager::GetRenderFrame lock ordering under fence stall."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path((root / '.local/headless-cache').read_text().strip()) / 'source'
cpp = (source / 'src/video_core/renderer_vulkan/vk_present_manager.cpp').read_text()
start = cpp.index('Frame* PresentManager::GetRenderFrame() {')
end = cpp.index('\nvoid PresentManager::Present(Frame* frame)', start)
method = cpp[start:end]
assert method.count('lock.unlock();') == 1
assert method.index('free_queue.pop_front();') < method.index('lock.unlock();') < method.index('frame->present_done.Wait();')

prefix = r'''#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <mutex>
#include <thread>
struct Fence {
    std::mutex mutex;
    std::condition_variable cv;
    bool signaled{};
    std::atomic<bool> waiting{};
    void Wait() {
        std::unique_lock lock(mutex);
        waiting = true;
        cv.wait(lock, [&] { return signaled; });
    }
    void Reset() { std::scoped_lock lock(mutex); signaled = false; }
    void Signal() { std::scoped_lock lock(mutex); signaled = true; cv.notify_all(); }
};
struct Frame { Fence present_done; };
struct PresentManager {
    std::mutex free_mutex;
    std::condition_variable free_cv;
    std::deque<Frame*> free_queue;
    Frame* GetRenderFrame();
};
'''
suffix = r'''
int main() {
    using namespace std::chrono_literals;
    for (int round = 0; round < 80; ++round) {
        PresentManager manager;
        Frame first, second;
        { std::scoped_lock lk(manager.free_mutex); manager.free_queue.push_back(&first); }
        std::atomic<Frame*> acquired{};
        std::thread producer([&] { acquired = manager.GetRenderFrame(); });
        auto deadline = std::chrono::steady_clock::now() + 2s;
        while (!first.present_done.waiting && std::chrono::steady_clock::now() < deadline)
            std::this_thread::yield();
        if (!first.present_done.waiting) return 3;
        std::atomic<bool> returned_other{};
        std::thread presenter([&] {
            { std::scoped_lock lk(manager.free_mutex); manager.free_queue.push_back(&second); }
            returned_other = true;
            manager.free_cv.notify_one();
        });
        deadline = std::chrono::steady_clock::now() + 75ms;
        while (!returned_other && std::chrono::steady_clock::now() < deadline)
            std::this_thread::yield();
        const bool unlocked_during_fence = returned_other;
        // Guarantee progress even on the original buggy implementation.
        first.present_done.Signal();
        presenter.join();
        producer.join();
        if (!unlocked_during_fence) {
            std::fprintf(stderr, "free_mutex held during fence at round %d\n", round);
            return 2;
        }
        if (acquired != &first || manager.free_queue.size() != 1 || manager.free_queue.front() != &second)
            return 4;
    }
    std::puts("Actual Vulkan GetRenderFrame: 80 fence-stall/parallel-return cases PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='eden-vk-fence-test-') as tmp:
    work = Path(tmp)
    (work / 'fence.cpp').write_text(prefix + method + suffix)
    binary = work / 'fence'
    env = os.environ.copy()
    if sys.platform == 'darwin' and not env.get('SDKROOT'):
        for name in ('MacOSX15.4.sdk', 'MacOSX15.sdk'):
            candidate = Path('/Library/Developer/CommandLineTools/SDKs') / name
            if candidate.is_dir():
                env['SDKROOT'] = str(candidate)
                break
    subprocess.run(['c++', '-std=c++20', '-O1', '-pthread', '-Wall', '-Wextra',
                    str(work / 'fence.cpp'), '-o', str(binary)], check=True, env=env)
    subprocess.run([str(binary)], check=True, timeout=15)
