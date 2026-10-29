#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stress REAL PresentManager queue/worker methods extracted from active Vulkan C++.

Builds the exact get-frame, enqueue, present-worker and drain methods with
host-only Vulkan/fence stand-ins. The scheduler.Record callback is invoked
immediately (optimistically), while CopyToSwapchain simulates measured
presentation latencies. Thus the test can prove a disconnect between the
COMPOSITOR CALLBACK and later PRESENTATION, not actual hardware jitter.
No game, driver, network, console or native executable is required.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
header=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_present_manager.h").read_text()
native_main=(root/"headless/main.cpp").read_text()
render=(root/"vendor/encore-active/eden-vulkan/vulkan_renderer.cpp").read_text()
assert "MAX_FRAMES_IN_FLIGHT = 7;" in active
assert "image_count = std::min<size_t>(swapchain.GetImageCount(), MAX_FRAMES_IN_FLIGHT);" in active
swap=(root/"vendor/encore-active/eden-vulkan/vulkan_swapchain.cpp").read_text()
assert "requested_image_count = (std::max)(requested_image_count, 3U);" in swap
assert "image_count = static_cast<u32>(images.size());" in swap
assert "std::jthread present_thread;" in header
assert "Settings::values.async_presentation = backend == Eden::GraphicsBackend::Vulkan;" in native_main
assert "SCOPE_EXIT {\n        render_window.OnFrameDisplayed();" in render
assert render.index("render_window.OnFrameDisplayed();") < render.index("present_manager.Present(frame);")

def method(start:str,stop:str):
    assert active.count(start)==1 and active.count(stop)==1, (start,stop)
    a=active.index(start)
    b=active.index(stop,a)
    return active[a:b]
methods=[
    method("Frame* PresentManager::GetRenderFrame() {","void PresentManager::Present(Frame* frame) {"),
    method("void PresentManager::Present(Frame* frame) {","size_t PresentManager::MaxExtraFrames() const {"),
    method("void PresentManager::WaitPresent() {","void PresentManager::PresentThread(std::stop_token token) {"),
    method("void PresentManager::PresentThread(std::stop_token token) {","void PresentManager::RecreateSwapchain(Frame* frame) {")
]
source=r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <exception>
#include <memory>
#include <mutex>
#include <stop_token>
#include <thread>
#include <utility>
#include <vector>
using namespace std::chrono_literals;
namespace vk { struct CommandBuffer {}; }
namespace Common {
enum class ThreadPriority { High };
void SetCurrentThreadName(const char*) {}
void SetCurrentThreadPriority(ThreadPriority) {}
void SetCurrentThreadToPerformanceCores() {}
}
namespace Eden::Performance {
inline int gpu_present_wait=0, gpu_present_free_wait=0, gpu_present_fence_wait=0;
struct DiagnosticTimer { explicit DiagnosticTimer(int&) {} };
}
struct Frame {
  unsigned index{};
  std::chrono::steady_clock::time_point callback;
  struct PresentFence { void Wait(){} void Reset(){} } present_done;
};
struct Scheduler {
  template<class F> void Record(F&& f){ f(vk::CommandBuffer{}); }
  void WaitWorker(){}
};
using Clock=std::chrono::steady_clock;
using Tick=Clock::time_point;
double Millis(Tick a,Tick b){
  return std::chrono::duration<double,std::milli>(b-a).count();
}
class PresentManager {
public:
  Scheduler scheduler;
  std::deque<Frame*> present_queue,free_queue;
  std::condition_variable_any frame_cv;
  std::condition_variable_any present_ready_cv;
  std::condition_variable free_cv;
  std::mutex swapchain_mutex,queue_mutex,free_mutex;
  bool present_in_flight{};
  bool use_present_thread{true};
  std::exception_ptr present_failure;
  std::jthread present_thread;
  std::vector<Frame> frames;
  std::vector<Tick> delivered;
  std::vector<double> latencies;
  std::mutex result_mutex;
  unsigned target_mode{};
  PresentManager(unsigned n,unsigned mode):frames(n),target_mode(mode) {
    for(unsigned i=0;i<n;i++){frames[i].index=i;free_queue.push_back(&frames[i]);}
    present_thread=std::jthread([this](std::stop_token token){PresentThread(token);});
  }
  ~PresentManager(){
    present_thread.request_stop();
    present_ready_cv.notify_all();
    if(present_thread.joinable())present_thread.join();
  }
  Frame* GetRenderFrame();
  void Present(Frame* frame);
  void WaitPresent();
  void PresentThread(std::stop_token token);
  void CopyToSwapchain(Frame* frame){
    // Baseline 2ms; a 130ms spike fits within a 7-frame 30Hz pool.
    // At mode=2 a 350ms spike should fill the pool and stall the callback.
    const unsigned ms=(frame->index==40 || frame->index==80 || frame->index==120)
      ? (target_mode==1?130u:target_mode==2?350u:2u):2u;
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
    std::scoped_lock lock{result_mutex};
    delivered.push_back(Clock::now());
    latencies.push_back(Millis(frame->callback,delivered.back()));
  }
};
__PRODUCTION_METHODS__
struct Outcome {
  double callback_max_ms{},present_gap_max_ms{},age_max_ms{};
  unsigned callback_count{},present_count{};
};
Outcome Run(unsigned mode,unsigned pool){
  PresentManager manager{pool,mode};
  constexpr unsigned count=150;
  constexpr auto cadence=std::chrono::microseconds(33333);
  std::vector<Tick> callbacks;
  const Tick start=Clock::now();
  for(unsigned i=0;i<count;i++){
    std::this_thread::sleep_until(start+i*cadence);
    Frame* frame=manager.GetRenderFrame();
    frame->index=i;
    frame->callback=Clock::now();
    // This event is "Composite callback" after enqueue, NOT a present ACK.
    manager.Present(frame);
    callbacks.push_back(Clock::now());
  }
  manager.WaitPresent();
  Outcome out{};
  out.callback_count=static_cast<unsigned>(callbacks.size());
  out.present_count=static_cast<unsigned>(manager.delivered.size());
  for(unsigned i=1;i<count;i++){
    out.callback_max_ms=std::max(out.callback_max_ms,Millis(callbacks[i-1],callbacks[i]));
  }
  for(unsigned i=1;i<manager.delivered.size();i++)
    out.present_gap_max_ms=std::max(out.present_gap_max_ms,
                                   Millis(manager.delivered[i-1],manager.delivered[i]));
  for(const double lag:manager.latencies) out.age_max_ms=std::max(out.age_max_ms,lag);
  return out;
}
int main(){
  const auto base3=Run(0,3);
  const auto short3=Run(1,3);
  const auto short7=Run(1,7);
  const auto oversize7=Run(2,7);
  for(auto [label,v]:{std::pair{"baseline_pool3",base3},std::pair{"130ms_pool3",short3},
                       std::pair{"130ms_pool7",short7},std::pair{"350ms_pool7",oversize7}}){
    std::printf("%s callbacks=%u presented=%u max_callback_gap_ms=%.2f "
                "max_present_gap_ms=%.2f max_async_age_ms=%.2f\n",label,
                v.callback_count,v.present_count,v.callback_max_ms,
                v.present_gap_max_ms,v.age_max_ms);
    assert(v.callback_count==150 && v.present_count==150);
  }
  // The tested 130ms intermittent present delay can remain INVISIBLE
  // to upstream callbacks, exactly as normal 30 FPS telemetry would.
  assert(short3.present_gap_max_ms>100.0);
  assert(short7.present_gap_max_ms>100.0);
  assert(short7.age_max_ms>125.0);
  // The actual swapchain image count is driver-returned. A small pool can
  // propagate the same delay upstream, a 7-image pool may conceal it.
  if(__STRICT_HOST_TIMING__) {
    // Wall-clock scheduling thresholds belong to a controlled local host run,
    // never an overloaded shared CI runner.
    assert(short3.callback_max_ms>55.0);
    assert(short7.callback_max_ms<50.0);
    assert(oversize7.callback_max_ms>60.0);
    assert(base3.present_gap_max_ms<80.0);
    std::puts("STRICT_HOST_TIMING_PASS: 3-vs-7 buffers differ under 130ms WSI hold");
  }
  std::puts("PASS: source-extracted presentation queues drain with 150/150 frames");
}
"""
source=source.replace("__PRODUCTION_METHODS__","\n".join(methods))
strict_host_timing = os.environ.get("EDEN_PRESENT_STRICT_HOST_TIMING") == "1"
source=source.replace("__STRICT_HOST_TIMING__","true" if strict_host_timing else "false")
assert "void PresentManager::PresentThread(std::stop_token token)" in source
assert "present_in_flight = false;" in source
assert "std::exchange(lock, std::unique_lock{swapchain_mutex})" in source
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"Host C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-async-present-replay-") as tmp:
    src=Path(tmp)/"present-replay.cpp"
    exe=Path(tmp)/"present-replay"
    src.write_text(source)
    subprocess.run([compiler,"-std=c++20","-O2","-pthread","-Wall","-Wextra","-Werror",
                    str(src),"-o",str(exe)],check=True,timeout=55)
    subprocess.run([str(exe)],check=True,timeout=32)
print("HOST-ONLY: actual Vulkan GPU completion, display scanout and in-game content not verified")
