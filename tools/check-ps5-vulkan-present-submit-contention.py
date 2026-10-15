#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove shared native Vulkan submit lock couples WSI present to GPU submission.

This is a source-anchored C++ scheduling counterexample with a MOCK blocking
WSI: NOT evidence that RADV actually blocks 130ms in FC27. Vulkan VkQueue
host external synchronization must be preserved, especially when the
graphics and presentation queue handles refer to the same VkQueue.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
swap=(root/"vendor/encore-active/eden-vulkan/vulkan_swapchain.cpp").read_text()
scheduler=(root/"vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
device=(root/"vendor/encore-active/eden-vulkan/vulkan_device.cpp").read_text()
s=swap[swap.index("void Swapchain::Present(VkSemaphore render_semaphore) {"):]
s=s[:s.index("\nbool Swapchain::")]
b=s.index("std::unique_lock<std::mutex> lock{scheduler.submit_mutex, std::defer_lock};")
assert "if (device.GetGraphicsFamily() == device.GetPresentFamily()) lock.lock();" in s
a=s.index("present_queue.Present(present_info)")
assert b<a
worker=scheduler[scheduler.index("u64 Scheduler::SubmitExecution("):]
worker=worker[:worker.index("\nvoid Scheduler::",5)]
assert worker.index("std::scoped_lock lock{submit_mutex};") < worker.index("master_semaphore->SubmitQueue(")
assert "graphics_queue = logical.GetQueue(graphics_family);" in device
assert "present_queue = logical.GetQueue(present_family);" in device
assert "::Common::unordered_set<u32> unique_queue_families{graphics_family, present_family};" in device
assert ".queueCount = 1," in device
# It is UNSAFE to just strip the mutex: both operations can use the same
# Vulkan VkQueue when graphics_family == present_family.
src=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <latch>
#include <mutex>
#include <thread>
using Clock=std::chrono::steady_clock;
using namespace std::chrono_literals;
double Ms(Clock::time_point a,Clock::time_point b) {
  return std::chrono::duration<double,std::milli>(b-a).count();
}
struct Result {double submit_delay_ms;unsigned long long independent_ipc;};
Result Run(unsigned mock_wsi_block_ms,bool same_queue){
    std::mutex submit_mutex;
    std::latch present_entered{1};
    std::atomic<bool> running{true};
    std::atomic<unsigned long long> independent_ipc{0};
    std::thread guest_ipc([&]{
      while(running.load(std::memory_order_relaxed)){
        independent_ipc.fetch_add(1,std::memory_order_relaxed);
        std::this_thread::yield();
      }
    });
    std::thread present([&]{
      // Stand-in for the actual Swapchain::Present's RAII critical section.
      std::unique_lock<std::mutex> lock{submit_mutex,std::defer_lock};
      if(same_queue) lock.lock();
      present_entered.count_down();
      std::this_thread::sleep_for(std::chrono::milliseconds(mock_wsi_block_ms));
    });
    present_entered.wait();
    const auto before=Clock::now();
    std::thread gpu_submit([&]{
      // Same RAII lock as actual Scheduler::SubmitExecution.
      std::scoped_lock lock{submit_mutex};
    });
    gpu_submit.join();
    const auto elapsed=Ms(before,Clock::now());
    present.join();
    running.store(false,std::memory_order_relaxed);
    guest_ipc.join();
    return {elapsed,independent_ipc.load(std::memory_order_relaxed)};
}
int main(){
  const auto normal=Run(5,true);
  const auto hitch=Run(130,true);
  const auto hard_stall=Run(350,true);
  const auto separate=Run(350,false);
  std::printf("MOCK_WSI 5ms gpu_submit_wait=%.2fms ipc=%llu\n",
              normal.submit_delay_ms,normal.independent_ipc);
  std::printf("MOCK_WSI 130ms gpu_submit_wait=%.2fms ipc=%llu\n",
              hitch.submit_delay_ms,hitch.independent_ipc);
  std::printf("MOCK_WSI 350ms gpu_submit_wait=%.2fms ipc=%llu\n",
              hard_stall.submit_delay_ms,hard_stall.independent_ipc);
  assert(hitch.submit_delay_ms>90);
  assert(hard_stall.submit_delay_ms>275);
  assert(separate.submit_delay_ms<200);
  assert(separate.submit_delay_ms<hard_stall.submit_delay_ms*0.7);
  assert(hitch.independent_ipc>0 && hard_stall.independent_ipc>0);
  std::puts("PASS: same-queue WSI lock maintained, cross-family GPU submit independent");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"Host C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-vulkan-present-submit-lock-") as tmp:
    source=Path(tmp)/"mutex.cpp";exe=Path(tmp)/"mutex"
    source.write_text(src)
    subprocess.run([compiler,"-std=c++20","-O2","-pthread","-Wall","-Wextra",
                    "-Werror",str(source),"-o",str(exe)],check=True,timeout=40)
    subprocess.run([str(exe)],check=True,timeout=8)
print("CONSTRAINT: independent queue benefit requires distinct Vulkan queue families; native WSI unmeasured")
