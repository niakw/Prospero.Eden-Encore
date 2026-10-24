#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05: native nvdisp -> GPU::Impl -> Host1x syncpoint composite replay.

Compile the actual nvdisp::Composite/WaitForComposite, GPU::Impl
RequestComposite/WaitForComposite, and SyncpointManager RegisterAction /
IncrementGuest / Increment C++ bodies together. External GPU scheduler,
Vulkan renderer, driver nvmap and timing are explicitly mocked.
No emulator game/SDK, scanout, GPU completion or FC27 performance proof.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NV = (ROOT/"vendor/sources/eden/src/core/hle/service/nvdrv/devices/nvdisp_disp0.cpp").read_text()
GPU = (ROOT/"vendor/sources/eden/src/video_core/gpu.cpp").read_text()
SYNC = (ROOT/"vendor/encore-active/eden-core/src/video_core/host1x/syncpoint_manager.cpp").read_text()
FAST = (ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL = (ROOT/".github/workflows/encore-core-preflight.yml").read_text()
NAME = "python3 -B tools/check-native-gpu-composite-syncpoint-host.py"
assert NAME in FAST and NAME in FULL

def extract(text, signature):
    assert text.count(signature) == 1, ("source drift", signature)
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for end in range(brace, len(text)):
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
            if depth == 0:
                return text[start:end+1]
    raise AssertionError(("unbalanced source", signature))

nv_methods = "\n".join(extract(NV, marker) for marker in (
    "void nvdisp_disp0::Composite(",
    "void nvdisp_disp0::WaitForComposite(",
))
gpu_methods = "\n".join(extract(GPU, marker) for marker in (
    "    void RequestComposite(",
    "    void WaitForComposite(",
))
sync_methods = "\n".join(extract(SYNC, marker) for marker in (
    "SyncpointManager::ActionHandle SyncpointManager::RegisterAction(",
    "void SyncpointManager::IncrementGuest(",
    "void SyncpointManager::Increment(",
))
assert "system.GPU().RequestComposite(std::move(output_layers), std::move(output_fences));" in nv_methods
assert "pending_composite_fence = RequestSyncOperation(" in gpu_methods
assert "syncpoint_manager.RegisterGuestAction(" in gpu_methods
assert "renderer->Composite(composite_layers);" in gpu_methods
assert "WaitForSyncOperation(fence);" in gpu_methods
assert "action();" in sync_methods and "ready.action();" in sync_methods

cpp = r"""
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <functional>
#include <list>
#include <memory>
#include <mutex>
#include <span>
#include <utility>
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
namespace Service::Nvidia {
struct NvFence { int id{-1}; u32 value{}; };
}
namespace Tegra {
enum class BlendMode { Opaque };
struct FramebufferConfig {
    u64 address{};
    int offset{},width{},height{},stride{},pixel_format{};
    int transform_flags{},crop_rect{};
    BlendMode blending{};
    int layer_stack_mask{};
};
namespace Host1x {
class SyncpointManager {
public:
    struct RegisteredAction {
        u32 expected_value{};
        std::function<void()> action;
        RegisteredAction(u32 v,std::function<void()>&& a)
            : expected_value(v),action(std::move(a)) {}
    };
    using ActionHandle=std::list<RegisteredAction>::iterator;
    std::array<std::atomic<u32>,192> syncpoints_guest{};
    std::array<std::list<RegisteredAction>,192> guest_action_storage;
    std::mutex guard;
    std::condition_variable wait_guest_cv;
    template<typename Func>
    ActionHandle RegisterGuestAction(u32 id,u32 expected,Func&& action) {
        return RegisterAction(syncpoints_guest[id],guest_action_storage[id],
                              expected,std::move(action));
    }
    ActionHandle RegisterAction(std::atomic<u32>&,std::list<RegisteredAction>&,
                                u32,std::function<void()>&&);
    void IncrementGuest(u32);
    void Increment(std::atomic<u32>&,std::condition_variable&,
                   std::list<RegisteredAction>&);
};
__SYNC_METHODS__
struct Host1x {
    SyncpointManager manager;
    SyncpointManager& GetSyncpointManager() {return manager;}
};
} // namespace Host1x
struct Renderer {
    std::vector<std::vector<u64>> deliveries;
    void Composite(std::span<const FramebufferConfig> layers) {
        std::vector<u64> ids;
        for (const auto& layer:layers) ids.push_back(layer.address);
        deliveries.push_back(std::move(ids));
    }
};
class GPU;
} // namespace Tegra
namespace Core {
struct PerfStats {
    unsigned ended{},begun{};
    void EndSystemFrame(){++ended;}
    void BeginSystemFrame(){++begun;}
};
struct SpeedLimiter {
    unsigned calls{};
    void DoSpeedLimiting(u64){++calls;}
};
struct CoreTiming {
    u64 GetGlobalTimeUs(){return 0;}
};
struct System {
    Tegra::GPU* gpu{};
    Tegra::Host1x::Host1x host;
    PerfStats perf;
    SpeedLimiter limiter;
    CoreTiming timing;
    Tegra::GPU& GPU();
    Tegra::Host1x::Host1x& Host1x(){return host;}
    PerfStats& GetPerfStats(){return perf;}
    SpeedLimiter& SpeedLimiter(){return limiter;}
    CoreTiming& CoreTiming(){return timing;}
};
} // namespace Core
namespace Tegra {
class GPU {
public:
    struct Impl {
        Core::System& system;
        Renderer* renderer{};
        bool is_async{true};
        std::atomic_bool shutting_down{};
        u64 pending_composite_fence{};
        u64 last_sync_fence{};
        u64 signaled_sync_fence{};
        unsigned wait_calls{},tick_calls{};
        std::deque<std::function<void()>> operations;
        std::deque<size_t> free_swap_counters;
        std::deque<size_t> request_swap_counters;
        std::mutex request_swap_mutex;
        struct Scheduler {
            Impl* impl{};
            void TickGPU(bool){++impl->tick_calls;impl->Drain();}
        } gpu_thread{this};
        explicit Impl(Core::System& s,Renderer& r):system(s),renderer(&r){}
        template<class F> u64 RequestSyncOperation(F&& f) {
            operations.emplace_back(std::forward<F>(f));
            return ++last_sync_fence;
        }
        void Drain() {
            while(!operations.empty()){
                auto fn=std::move(operations.front());
                operations.pop_front();
                fn();
                ++signaled_sync_fence;
            }
        }
        void WaitForSyncOperation(u64 fence){
            ++wait_calls;
            assert(signaled_sync_fence>=fence);
        }
__GPU_METHODS__
    };
    Impl impl;
    explicit GPU(Core::System& s,Renderer& r):impl(s,r){}
    void RequestComposite(std::vector<FramebufferConfig>&& layers,
                          std::vector<Service::Nvidia::NvFence>&& fences) {
        impl.RequestComposite(std::move(layers),std::move(fences));
    }
    void WaitForComposite(){impl.WaitForComposite();}
};
} // namespace Tegra
Tegra::GPU& Core::System::GPU(){assert(gpu);return *gpu;}
namespace Common::ADPF {
inline unsigned reports=0;
void ReportFrameInterval(){++reports;}
}
namespace Service::Nvnflinger {
struct Fence {
    size_t num_fences{};
    std::array<Nvidia::NvFence,4> fences{};
};
struct HwcLayer {
    int buffer_handle{},offset{},width{},height{},stride{},format{};
    int transform{},crop_rect{},blending{},layer_stack_mask{};
    Fence acquire_fence{};
};
}
namespace Service::Nvidia::Devices {
Tegra::BlendMode ConvertBlending(int){return Tegra::BlendMode::Opaque;}
struct NvMap {
    u64 GetHandleAddress(int id){return 0x100000ULL+static_cast<u64>(id);}
};
class nvdisp_disp0 {
public:
    Core::System& system;
    NvMap nvmap;
    explicit nvdisp_disp0(Core::System& s):system(s){}
    void Composite(std::span<const Service::Nvnflinger::HwcLayer>);
    void WaitForComposite();
};
__NV_METHODS__
} // namespace Service::Nvidia::Devices

static Service::Nvnflinger::HwcLayer MakeLayer(int handle,
                                              std::initializer_list<Service::Nvidia::NvFence> fences) {
    Service::Nvnflinger::HwcLayer layer{};
    layer.buffer_handle=handle;
    layer.width=1920;layer.height=1080;layer.stride=1920;
    layer.acquire_fence.num_fences=fences.size();
    assert(fences.size()<=layer.acquire_fence.fences.size());
    std::copy(fences.begin(),fences.end(),layer.acquire_fence.fences.begin());
    return layer;
}
int main() {
    Core::System system;
    Tegra::Renderer renderer;
    Tegra::GPU gpu(system,renderer);
    system.gpu=&gpu;
    Service::Nvidia::Devices::nvdisp_disp0 display(system);
    auto& sync=system.Host1x().GetSyncpointManager();
    using F=Service::Nvidia::NvFence;
    const auto submit=[&](std::initializer_list<Service::Nvnflinger::HwcLayer> layers){
        std::vector<Service::Nvnflinger::HwcLayer> list(layers);
        display.Composite(list);
        display.WaitForComposite();
    };
    // No guest fence => renderer receives native nvdisp mapping immediately.
    submit({MakeLayer(7,{})});
    assert(renderer.deliveries.size()==1);
    assert((renderer.deliveries.back()==std::vector<u64>{0x100007ULL}));
    assert(gpu.impl.request_swap_counters.empty());

    // Two distinct outstanding fences. RequestSyncOperation completes before
    // the raster work: WaitForComposite must NOT be treated as a present ACK.
    submit({MakeLayer(8,{F{4,1}}),MakeLayer(9,{F{5,1}})});
    assert(renderer.deliveries.size()==1 && gpu.impl.wait_calls==2);
    assert(gpu.impl.request_swap_counters.size()==1);
    sync.IncrementGuest(5);
    assert(renderer.deliveries.size()==1);
    sync.IncrementGuest(4);
    assert(renderer.deliveries.size()==2);
    assert((renderer.deliveries.back()==std::vector<u64>{0x100008ULL,0x100009ULL}));
    assert(gpu.impl.free_swap_counters.size()==1);

    // Duplicate syncpoint id, different thresholds, and invalid id filtering.
    submit({MakeLayer(10,{F{-1,123},F{6,1},F{6,2}})});
    assert(renderer.deliveries.size()==2);
    sync.IncrementGuest(6);
    assert(renderer.deliveries.size()==2);
    sync.IncrementGuest(6);
    assert(renderer.deliveries.size()==3 && renderer.deliveries.back()[0]==0x10000aULL);
    assert(gpu.impl.request_swap_counters.size()==1); // reuse released counter

    // Guest fence already satisfied at registration: real RegisterAction runs
    // it synchronously. Multiple callbacks must still publish only ONE frame.
    submit({MakeLayer(11,{F{4,1},F{5,1}})});
    assert(renderer.deliveries.size()==4);
    assert(renderer.deliveries.back()[0]==0x10000bULL);

    // Long stress: alternate deferred and immediate fence paths. No phantom
    // completion and no unbounded growth of request counter slots.
    for(u32 i=0;i<256;++i){
        const u32 required=i+1;
        submit({MakeLayer(100+static_cast<int>(i),{F{9,required},F{10,required}})});
        const auto prior=renderer.deliveries.size();
        sync.IncrementGuest(10);
        assert(renderer.deliveries.size()==prior);
        sync.IncrementGuest(9);
        assert(renderer.deliveries.size()==prior+1);
        assert(gpu.impl.request_swap_counters.size()==1);
        assert(gpu.impl.free_swap_counters.size()==1);
    }
    assert(system.perf.ended==260 && system.perf.begun==260);
    assert(system.limiter.calls==260);
    assert(Common::ADPF::reports==260);
    assert(gpu.impl.wait_calls==260);
    assert(gpu.impl.tick_calls==260);
    assert(renderer.deliveries.size()==260);
    std::puts("F05_NV_DISP_GPU_SYNCPOINT_SOURCE_PASS requests=260 delayed_and_immediate_fences=verified");
    std::puts("F05_PRESENT_ACK_NOT_PROVEN host_GPU_request_completion_precedes_guest_fence_callback");
}
"""
cpp=cpp.replace("__NV_METHODS__",nv_methods)
cpp=cpp.replace("__GPU_METHODS__",gpu_methods)
cpp=cpp.replace("__SYNC_METHODS__",sync_methods)
assert "__GPU_METHODS__" not in cpp and "__NV_METHODS__" not in cpp
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f05-native-syncpoint-") as temp:
    src=Path(temp)/"native.cpp"
    src.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(temp)/("f05"+opt)
        build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra",
                              "-Werror","-pthread","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(src),"-o",str(exe)],
                             capture_output=True,text=True,timeout=50)
        assert build.returncode==0,(opt,build.stderr[-4500:])
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=25)
        assert run.returncode==0,(opt,run.stderr[-3000:])
        print(run.stdout.strip(),opt)
