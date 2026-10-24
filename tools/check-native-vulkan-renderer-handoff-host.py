#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05: source-extracted Vulkan renderer -> async presentation ownership replay.

Compile real RendererVulkan::Composite plus PresentManager::{GetRenderFrame,
Present, WaitPresent, PresentThread} in ONE C++20 executable at -O0 and -O2.
Only GPU draw calls, swapchain/copy, scheduling and timing are host stand-ins.
This distinguishes OnFrameDisplayed callbacks from completed host copies.
No real Vulkan WSI, GPU work, HLE guest frame pacing, or PS5 gameplay proof.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RENDER = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_renderer.cpp").read_text()
PRESENT = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
FAST = (ROOT / ".github/workflows/encore-core-fast-gate.yml").read_text()
FULL = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
INVOCATION = "python3 -B tools/check-native-vulkan-renderer-handoff-host.py"
assert INVOCATION in FAST and INVOCATION in FULL
assert "vulkan_present_manager.cpp" in (ROOT / "headless/vulkan.cmake").read_text()
assert "vulkan_renderer.cpp" in (ROOT / "headless/vulkan.cmake").read_text()

def native(text: str, start: str) -> str:
    assert text.count(start) == 1, ("source drift", start)
    begin = text.index(start)
    brace = text.index("{", begin)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[begin:index + 1]
    raise AssertionError("Unbalanced source: " + start)

methods = "\n\n".join(native(PRESENT, m) for m in (
    "Frame* PresentManager::GetRenderFrame() {",
    "void PresentManager::Present(Frame* frame) {",
    "void PresentManager::WaitPresent() {",
    "void PresentManager::PresentThread(std::stop_token token) {",
))
composite = native(RENDER, "void RendererVulkan::Composite(")
assert "SCOPE_EXIT" in composite and "render_window.OnFrameDisplayed();" in composite
assert composite.index("render_window.OnFrameDisplayed();") < composite.index("present_manager.Present(frame);")
assert "present_manager.GetRenderFrame()" in composite
assert "present_manager.Present(frame);" in composite
assert "scheduler.DispatchWork();" in composite
assert "if (::Eden::Display::SkipFrame())" in composite
assert "present_in_flight = false;" in methods
assert "CopyToSwapchain(frame);" in methods
assert "free_queue.push_back(frame);" in methods
assert "frame_cv.notify_all();" in methods

cpp = r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <exception>
#include <memory>
#include <mutex>
#include <span>
#include <stop_token>
#include <thread>
#include <utility>
#include <vector>
using namespace std::chrono_literals;
namespace vk {struct CommandBuffer {};}
namespace Common {
enum class ThreadPriority { High };
void SetCurrentThreadName(const char*) {}
void SetCurrentThreadPriority(ThreadPriority) {}
void SetCurrentThreadToPerformanceCores() {}
}
namespace Eden::Performance {
inline int gpu_present_wait{},gpu_present_free_wait{},gpu_present_fence_wait{};
struct DiagnosticTimer {explicit DiagnosticTimer(int&) {}};
}
namespace Eden::Display {
inline bool skip{};
bool SkipFrame() {return skip;}
}
template<class F> struct ScopeGuard {F f;~ScopeGuard(){f();}};
struct ScopeTag {};
template<class F> ScopeGuard<F> operator+(ScopeTag,F f) {return {std::move(f)};}
#define ENCORE_JOIN_IMPL(a,b) a##b
#define ENCORE_JOIN(a,b) ENCORE_JOIN_IMPL(a,b)
#define SCOPE_EXIT [[maybe_unused]] auto ENCORE_JOIN(_exit_,__LINE__) = ScopeTag{} + [&]()
namespace Tegra {
struct FramebufferConfig {std::uint64_t address{};};
}
struct Frame {
    std::uint32_t game{},hud{},index{};
    inline static int ready{};
    int* render_ready{&ready};
    struct PresentFence {void Wait(){}void Reset(){}} present_done;
};
struct Scheduler {
    unsigned flushes{},dispatches{},request_context{};
    template<class F> void Record(F&& f){f(vk::CommandBuffer{});}
    void WaitWorker(){}
    void Flush(int) {++flushes;}
    void DispatchWork(){++dispatches;}
    void RequestOutsideRenderPassOperationContext(){++request_context;}
};
class PresentManager {
public:
    Scheduler scheduler;
    std::deque<Frame*> present_queue,free_queue;
    std::condition_variable_any frame_cv;
    std::condition_variable free_cv;
    std::mutex swapchain_mutex,queue_mutex,free_mutex;
    bool present_in_flight{};
    bool use_present_thread{true};
    std::exception_ptr present_failure;
    std::jthread present_thread;
    std::vector<Frame> frames;
    std::vector<std::pair<std::uint32_t,std::uint32_t>> presented;
    std::mutex result_mutex;
    std::mutex hold_mutex;
    std::condition_variable hold_cv;
    bool hold_copy{};
    unsigned copies{};
    explicit PresentManager(size_t count):frames(count) {
        for(auto& f:frames)free_queue.push_back(&f);
        present_thread=std::jthread([this](std::stop_token token){PresentThread(token);});
    }
    ~PresentManager(){
        {
            std::lock_guard lock{hold_mutex};
            hold_copy=false;
        }
        hold_cv.notify_all();
        present_thread.request_stop();
        frame_cv.notify_all();
        if(present_thread.joinable())present_thread.join();
    }
    int SwapchainImageCount()const{return 3;}
    int SwapchainImageViewFormat()const{return 1;}
    Frame* GetRenderFrame();
    void Present(Frame*);
    void WaitPresent();
    void PresentThread(std::stop_token);
    void CopyToSwapchain(Frame* frame){
        // Deterministic blocked-copy path separates callback from delivery,
        // with no driver timing or fake FPS measurement.
        {
            std::unique_lock lock{hold_mutex};
            hold_cv.wait(lock,[this]{return !hold_copy;});
        }
        std::lock_guard lock{result_mutex};
        presented.emplace_back(frame->game,frame->hud);
        ++copies;
    }
};
__PRESENT_METHODS__
struct RenderWindow {
    bool shown{true};
    unsigned displayed{};
    void OnFrameDisplayed(){++displayed;}
    bool IsShown()const{return shown;}
    int GetFramebufferLayout()const{return 0;}
};
struct GPU {
    unsigned notifications{};
    void RendererFrameEndNotify(){++notifications;}
};
struct Rasterizer {
    unsigned ticks{};
    void TickFrame(){++ticks;}
};
struct Device {};
struct Blit {
    unsigned draws{};
    void DrawToFrame(Device&,Rasterizer&,Frame* frame,
                     std::span<const Tegra::FramebufferConfig> layers,
                     int,int,int,bool) {
        assert(layers.size()==2);
        frame->game=static_cast<std::uint32_t>(layers[0].address);
        frame->hud=static_cast<std::uint32_t>(layers[1].address);
        ++draws;
    }
};
class RendererVulkan {
public:
    PresentManager& present_manager;
    RenderWindow render_window;
    Scheduler scheduler;
    GPU gpu;
    Rasterizer rasterizer;
    Device device;
    Blit blit_swapchain;
    unsigned captures{},screenshots{};
    explicit RendererVulkan(PresentManager& p):present_manager(p){}
    void RenderAppletCaptureLayer(std::span<const Tegra::FramebufferConfig>){++captures;}
    void RenderScreenshot(std::span<const Tegra::FramebufferConfig>){++screenshots;}
    void Composite(std::span<const Tegra::FramebufferConfig>);
};
__RENDER_METHOD__
static void Deliver(RendererVulkan& renderer,std::uint32_t game,std::uint32_t hud) {
    const Tegra::FramebufferConfig pair[]={{game},{hud}};
    renderer.Composite(pair);
}
int main(){
    PresentManager present{7};
    RendererVulkan renderer{present};
    // OnFrameDisplayed is a GPU-worker callback, not a swapchain ACK.
    // Hold the real PresentThread's copy while the callback returns.
    {
        std::lock_guard lock{present.hold_mutex};
        present.hold_copy=true;
    }
    Deliver(renderer,100,200);
    assert(renderer.render_window.displayed==1);
    assert(present.presented.empty());
    {
        std::lock_guard lock{present.hold_mutex};
        present.hold_copy=false;
    }
    present.hold_cv.notify_all();
    present.WaitPresent();
    assert((present.presented==std::vector<std::pair<std::uint32_t,std::uint32_t>>{{100,200}}));

    constexpr unsigned ticks=240;
    std::vector<std::pair<std::uint32_t,std::uint32_t>> expected={{100,200}};
    std::uint32_t game=100;
    for(unsigned tick=0;tick<ticks;++tick){
        const bool paused=tick>=100 && tick<112;
        if(!paused && tick%2==0) ++game; // game every 2 ticks, HUD every tick
        const std::uint32_t hud=2000+tick;
        Deliver(renderer,game,hud);
        expected.emplace_back(game,hud);
        if(paused) assert(game==150);
    }
    present.WaitPresent();
    assert(present.presented==expected);
    assert(present.copies==ticks+1);
    assert(renderer.render_window.displayed==ticks+1);
    assert(renderer.gpu.notifications==ticks+1);
    assert(renderer.rasterizer.ticks==ticks+1);
    assert(renderer.scheduler.dispatches==ticks+1);
    assert(renderer.blit_swapchain.draws==ticks+1);
    {
        std::lock_guard lock{present.queue_mutex};
        assert(present.present_queue.empty() && !present.present_in_flight);
    }
    {
        std::lock_guard lock{present.free_mutex};
        assert(present.free_queue.size()==7);
    }

    // Skipped and hidden frames must not enter the Vulkan present queue.
    Eden::Display::skip=true;
    Deliver(renderer,900,901);
    Eden::Display::skip=false;
    renderer.render_window.shown=false;
    Deliver(renderer,902,903);
    renderer.render_window.shown=true;
    present.WaitPresent();
    assert(present.presented==expected);
    assert(renderer.render_window.displayed==ticks+3);
    assert(renderer.gpu.notifications==ticks+2);
    assert(renderer.rasterizer.ticks==ticks+2);
    assert(renderer.blit_swapchain.draws==ticks+1);
    std::printf("F05_VULKAN_RENDER_PRESENT_HOST_PASS frames=%u callbacks=%u "
                "game_hz=30 hud_hz=60 pause_ticks=12 pool=7\n",
                present.copies,renderer.render_window.displayed);
    std::puts("F05_VULKAN_WSI_NOT_PROVEN real_gpu_and_scanout_unmeasured");
}
"""
cpp=cpp.replace("__PRESENT_METHODS__",methods).replace("__RENDER_METHOD__",composite)
assert "__PRESENT_METHODS__" not in cpp and "__RENDER_METHOD__" not in cpp
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f05-vulkan-present-") as tmp:
    src=Path(tmp)/"replay.cpp"
    src.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/("present"+opt)
        built=subprocess.run([compiler,"-std=c++20",opt,"-pthread","-Wall","-Wextra",
                              "-Werror","-fsanitize=undefined","-fno-sanitize-recover=all",
                              str(src),"-o",str(exe)],capture_output=True,text=True,timeout=75)
        assert built.returncode==0,(opt,built.stderr[-5000:])
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        assert run.returncode==0,(opt,run.stderr[-3500:])
        print(run.stdout.strip(),opt)
