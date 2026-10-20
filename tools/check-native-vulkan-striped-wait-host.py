#!/usr/bin/env python3
"""Compile real maintained pipeline striped locks under ASan/UBSan.

Two pipelines deliberately share a condition slot. A wake for one must
not release the other predicate or strand a waiter. Host-only semantics.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
HEADER=ROOT/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/striped_wait.h"
SOURCE=HEADER.read_text()
GFX=(ROOT/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
COMPUTE=(ROOT/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_compute_pipeline.h").read_text()
CI=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-native-vulkan-striped-wait-host.py" in CI
assert "::Eden::StripedCondition build_condvar;" in GFX and "::Eden::StripedMutex build_mutex;" in GFX
assert "::Eden::StripedCondition build_condvar;" in COMPUTE and "::Eden::StripedMutex build_mutex;" in COMPUTE
assert "inline constexpr std::size_t kSlots = 64;" in SOURCE
assert "ConditionFor(this).notify_all();" in SOURCE
assert "ConditionFor(this).wait(lock, std::move(predicate));" in SOURCE
CODE=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <type_traits>
#include <vector>
#include "video_core/renderer_vulkan/striped_wait.h"
struct Pipeline {
    Eden::StripedCondition condition;
    Eden::StripedMutex mutex;
    bool ready=false;
};
static_assert(sizeof(Eden::StripedCondition)==sizeof(std::condition_variable));
static_assert(sizeof(Eden::StripedMutex)==sizeof(std::mutex));
int main(){
    std::array<Pipeline*,Eden::StripedWait::kSlots> collisions{};
    std::vector<std::unique_ptr<Pipeline>> pipelines;
    Pipeline *a=nullptr,*b=nullptr;
    for(int i=0;i<4096 && !a;++i){
        auto p=std::make_unique<Pipeline>();
        auto slot=Eden::StripedWait::SlotOf(&p->condition);
        if(collisions[slot]){a=collisions[slot];b=p.get();}
        else collisions[slot]=p.get();
        pipelines.push_back(std::move(p));
    }
    assert(a && b && a!=b);
    assert(&Eden::StripedWait::ConditionFor(&a->condition)==
           &Eden::StripedWait::ConditionFor(&b->condition));
    std::atomic<int> entered{0};
    std::atomic<bool> done_a{false},done_b{false};
    auto worker=[&](Pipeline* p,std::atomic<bool>& flag){
        std::unique_lock<Eden::StripedMutex> guard{p->mutex};
        entered.fetch_add(1,std::memory_order_release);
        p->condition.wait(guard,[&]{return p->ready;});
        flag.store(true,std::memory_order_release);
    };
    std::thread ta(worker,a,std::ref(done_a));
    std::thread tb(worker,b,std::ref(done_b));
    using namespace std::chrono_literals;
    auto deadline=std::chrono::steady_clock::now()+4s;
    while(entered.load(std::memory_order_acquire)!=2 &&
          std::chrono::steady_clock::now()<deadline)std::this_thread::yield();
    assert(entered.load()==2);
    {std::scoped_lock lock{a->mutex};a->ready=true;}
    a->condition.notify_one();
    while(!done_a.load(std::memory_order_acquire) &&
          std::chrono::steady_clock::now()<deadline)std::this_thread::yield();
    assert(done_a.load() && !done_b.load());
    {std::scoped_lock lock{b->mutex};b->ready=true;}
    b->condition.notify_one();
    while(!done_b.load(std::memory_order_acquire) &&
          std::chrono::steady_clock::now()<deadline)std::this_thread::yield();
    assert(done_b.load());
    ta.join();tb.join();
    for(const auto& p:pipelines){
        const auto slot=Eden::StripedWait::SlotOf(&p->condition);
        assert(slot<Eden::StripedWait::kSlots);
    }
    return 0;
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-striped-wait-") as temp:
    root=Path(temp)
    src=root/"striped.cpp"
    exe=root/"striped"
    src.write_text(CODE)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-pthread",
                    "-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    "-I",str(HEADER.parents[2]),str(src),"-o",str(exe)],
                   check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("ENCORE_VULKAN_STRIPED_WAIT_HOST_PASS; console latency unmeasured")
