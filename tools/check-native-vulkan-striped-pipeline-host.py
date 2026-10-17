#!/usr/bin/env python3
"""Stress source-maintained Vulkan striped build waits under GCC and Clang.

Checks shared primitive ceilings and independent predicate wakeups. Not a
console FPS or driver-thread-limit test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active/eden-vulkan"
hdir = active / "include/video_core/renderer_vulkan"
cmake = (root/"headless/vulkan.cmake").read_text()
workflow = (root/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-native-vulkan-striped-pipeline-host.py" in workflow
assert 'file(COPY ' in cmake and 'DESTINATION ' in cmake
assert "EDEN_ACTIVE_VULKAN" in cmake and "target_include_directories(video_core BEFORE PUBLIC" in cmake
helper = (hdir/"striped_wait.h").read_text()
assert "kSlots = 64;" in helper
assert "notify_one() noexcept { StripedWait::ConditionFor(this).notify_all(); }" in helper
assert "static_assert(sizeof(StripedMutex) == sizeof(std::mutex)" in helper
assert "static_assert(sizeof(StripedCondition) == sizeof(std::condition_variable)" in helper

for name in ("vk_graphics_pipeline.h", "vk_compute_pipeline.h"):
    code=(hdir/name).read_text()
    assert code.count('#include "video_core/renderer_vulkan/striped_wait.h"') == 1
    assert code.count("::Eden::StripedCondition build_condvar;") == 1
    assert code.count("::Eden::StripedMutex build_mutex;") == 1
    assert "std::condition_variable build_condvar;" not in code
    assert "std::mutex build_mutex;" not in code
for name in ("vk_graphics_pipeline_cost.cpp", "vk_compute_pipeline_cost.cpp"):
    code=(active/name).read_text()
    assert "std::unique_lock lock{build_mutex};" in code
    assert "build_condvar.wait(lock, [this] {" in code
    assert "build_condvar.notify_all();" in code

cpp=r"""
#include "video_core/renderer_vulkan/striped_wait.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <memory>
#include <set>
#include <thread>
#include <vector>
struct Pipeline {
    Eden::StripedCondition build_condvar;
    Eden::StripedMutex build_mutex;
    std::atomic_bool is_built{false};
};
int main() {
    constexpr int kPipelines=8192, kWaiters=96;
    auto p=std::make_unique<Pipeline[]>(kPipelines);
    std::set<void*> mutexes,conditions;
    for(int i=0;i<kPipelines;++i) {
        mutexes.insert(&Eden::StripedWait::MutexFor(&p[i].build_mutex));
        conditions.insert(&Eden::StripedWait::ConditionFor(&p[i].build_condvar));
    }
    assert(mutexes.size()<=64 && conditions.size()<=64);
    assert(mutexes.size()>1 && conditions.size()>1);
    std::atomic<int> entered{0},complete{0};
    std::vector<std::thread> threads;
    for(int i=0;i<kWaiters;++i)threads.emplace_back([&,i]{
        auto& item=p[i*5];
        std::unique_lock lock{item.build_mutex};
        entered.fetch_add(1,std::memory_order_release);
        item.build_condvar.wait(lock,[&item]{
            return item.is_built.load(std::memory_order_relaxed);
        });
        assert(item.is_built.load(std::memory_order_acquire));
        complete.fetch_add(1,std::memory_order_release);
    });
    while(entered.load(std::memory_order_acquire)!=kWaiters)
        std::this_thread::yield();
    for(int i=kWaiters-1;i>=0;--i) {
        auto& item=p[i*5];
        {
            std::scoped_lock lock{item.build_mutex};
            item.is_built.store(true,std::memory_order_release);
        }
        // This must broadcast because other pipelines share the condition.
        item.build_condvar.notify_one();
    }
    for(auto& t:threads)t.join();
    assert(complete.load()==kWaiters);
    bool collision=false;
    for(int i=0;i<kPipelines && !collision;++i)
      for(int j=i+1;j<kPipelines;++j)
        if(&Eden::StripedWait::ConditionFor(&p[i].build_condvar)
           ==&Eden::StripedWait::ConditionFor(&p[j].build_condvar)){
           collision=true;break;
        }
    assert(collision);
    std::printf("NATIVE_VULKAN_STRIPED_PIPELINES_PASS count=%d waiters=%d locks=%zu conditions=%zu\n",
                kPipelines,kWaiters,mutexes.size(),conditions.size());
}
"""
compilers=[x for x in (shutil.which("g++"),shutil.which("clang++")) if x]
assert compilers
with tempfile.TemporaryDirectory(prefix="encore-striped-wait-") as d:
    tmp=Path(d)
    src=tmp/"stripe.cpp"
    src.write_text(cpp)
    for compiler in compilers:
        for opt in (0,2):
            binary=tmp/(Path(compiler).name+"-"+str(opt))
            subprocess.run([compiler,"-std=c++20","-O"+str(opt),"-pthread","-Wall",
                            "-Wextra","-Werror","-fsanitize=undefined",
                            "-fno-sanitize-recover=all","-I",str(active/"include"),
                            str(src),"-o",str(binary)],check=True,timeout=50)
            output=subprocess.run([str(binary)],capture_output=True,text=True,
                                  timeout=20,check=True)
            assert "NATIVE_VULKAN_STRIPED_PIPELINES_PASS" in output.stdout
            print(Path(compiler).name,"O"+str(opt),output.stdout.strip())
print("VULKAN_STRIPED_PIPELINE_HOST_ONLY_NO_CONSOLE_FPS_PROOF")
