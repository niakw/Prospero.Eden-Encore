#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the EXACT generated native VkAcquireNextImageKHR body with fake WSI.

Tests healthy/suboptimal/outdated/error, transient unavailable images,
terminal 10-second budget, semaphore/index validity and fallback parity.
This does not pretend the host has a PS5 Vulkan driver or real wall time.
"""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
pinned=(root/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_swapchain.cpp").read_text()
tree=ast.parse((root/"tools/prepare-vulkan-port.py").read_text())
adapt_calls=[
    n.value for n in tree.body
    if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
    and isinstance(n.value.func,ast.Name) and n.value.func.id=="adapt"
    and len(n.value.args)==3 and isinstance(n.value.args[0],ast.Constant)
    and n.value.args[0].value=="src/video_core/renderer_vulkan/vk_swapchain.cpp"
]
assert len(adapt_calls)==1
assert ast.literal_eval(adapt_calls[0].args[1])=="vulkan_swapchain.cpp"
replacements=ast.literal_eval(adapt_calls[0].args[2])
generated=pinned
for before,after in replacements:
    assert generated.count(before)==1, f"Pinned Vulkan adapter drift: {before[:80]}"
    generated=generated.replace(before,after)
a=generated.index("bool Swapchain::AcquireNextImage() {")
b=generated.index("\nvoid Swapchain::Present(",a)
body=generated[a:b]
assert "constexpr u64 kAcquireSliceNs = 250'000'000ULL;" in body
assert "constexpr u32 kMaxAcquireTimeouts = 40;" in body
assert "throw vk::Exception(VK_TIMEOUT);" in body
assert body.index("if (result == VK_TIMEOUT || result == VK_NOT_READY)") < body.index("switch (result)")
assert body.count("    case VK_ERROR_OUT_OF_DATE_KHR:")==1
assert "is_outdated = true;\n        return true;" in body
assert body.index("is_outdated = true;\n        return true;") < body.index("resource_ticks[image_index]")
assert "#ifdef PS5_NATIVE" in body and "#else" in body and "#endif" in body
assert "vk::Check(result);" in body # actual fatal errors still propagated
assert "resource_ticks[image_index] = scheduler.CurrentTick();" in body

stub=r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <limits>
#include <memory>
#include <stdexcept>
#include <vector>
using u64=std::uint64_t;
using u32=std::uint32_t;
enum VkResult : int { VK_SUCCESS=0,VK_NOT_READY=1,VK_TIMEOUT=2,
  VK_SUBOPTIMAL_KHR=1000001003,VK_ERROR_OUT_OF_DATE_KHR=-1000001004,
  VK_ERROR_SURFACE_LOST_KHR=-1000000000 };
constexpr int VK_NULL_HANDLE=0;
#define LOG_ERROR(...) ((void)0)
const char* string_VkResult(VkResult){return "simulated";}
namespace vk {
struct Exception:std::exception{
  VkResult result;
  explicit Exception(VkResult value):result(value){}
  const char* what()const noexcept override{return "mock Vulkan error";}
  VkResult GetResult() const noexcept{return result;}
};
void Check(VkResult result){if(result!=VK_SUCCESS)throw Exception(result);}
}
namespace Settings {
enum class FramePacingMode{Target_Auto,Target_30,Target_60,Target_90,Target_120};
struct Mode {
 FramePacingMode value{FramePacingMode::Target_Auto};
 FramePacingMode GetValue() const{return value;}
};
struct Values{Mode frame_pacing_mode;};
inline Values values{};
}
struct FakeLogical {
  std::vector<VkResult> results;
  unsigned calls{};
  std::vector<u64> timeouts;
  unsigned successes{};
  VkResult AcquireNextImageKHR(int,u64 timeout,int,int,u32* index){
    ++calls;
    timeouts.push_back(timeout);
    if(calls>results.size())throw std::runtime_error("unscripted Vulkan acquire");
    VkResult result=results[calls-1];
    if(result==VK_SUCCESS||result==VK_SUBOPTIMAL_KHR){*index=1;++successes;}
    return result;
  }
};
struct Device {
  FakeLogical logical;
  FakeLogical& GetLogical(){return logical;}
};
struct Scheduler {
  unsigned waits{};
  std::vector<u64> ticks{7,8,9};
  u64 CurrentTick()const{return 77;}
  void Wait(u64, double=0){++waits;}
};
class Swapchain {
public:
  std::shared_ptr<int> swapchain{std::make_shared<int>(17)};
  std::vector<std::shared_ptr<int>> present_semaphores{std::make_shared<int>(4)};
  unsigned frame_index{};
  u32 image_index{std::numeric_limits<u32>::max()};
  bool is_suboptimal{},is_outdated{};
  Device device;
  Scheduler scheduler;
  std::vector<u64> resource_ticks{7,8,9};
  bool AcquireNextImage();
};
__REAL_METHOD__
int main(){
  {
    Swapchain s;
    s.device.logical.results={VK_SUCCESS};
    assert(!s.AcquireNextImage());
    assert(s.device.logical.calls==1 && s.device.logical.successes==1);
    assert(s.image_index==1 && s.resource_ticks[1]==77 && s.scheduler.waits==1);
  }
  {
    Swapchain s;
    s.device.logical.results={VK_ERROR_OUT_OF_DATE_KHR};
    assert(s.AcquireNextImage() && s.is_outdated);
    assert(s.image_index==std::numeric_limits<u32>::max());
    assert(s.device.logical.successes==0 && s.scheduler.waits==0);
    assert(s.resource_ticks[1]==8);
  }
  {
    Swapchain s;
    s.device.logical.results={VK_SUBOPTIMAL_KHR};
    assert(s.AcquireNextImage() && s.is_suboptimal && s.image_index==1);
    assert(s.scheduler.waits==1);
  }
#ifdef PS5_NATIVE
  {
    Swapchain s;
    s.device.logical.results={VK_TIMEOUT,VK_NOT_READY,VK_TIMEOUT,VK_SUCCESS};
    assert(!s.AcquireNextImage());
    assert(s.device.logical.calls==4 && s.device.logical.successes==1);
    assert(s.scheduler.waits==1 && s.resource_ticks[1]==77);
    for(auto ns:s.device.logical.timeouts)assert(ns==250'000'000ULL);
  }
  {
    Swapchain s;
    s.device.logical.results.assign(40,VK_TIMEOUT);
    bool caught=false;
    try{(void)s.AcquireNextImage();}catch(const vk::Exception& e){caught=e.GetResult()==VK_TIMEOUT;}
    assert(caught && s.device.logical.calls==40);
    assert(s.device.logical.successes==0 && s.scheduler.waits==0);
    assert(s.image_index==std::numeric_limits<u32>::max());
    assert(s.resource_ticks[1]==8);
  }
  {
    Swapchain s;
    s.device.logical.results={VK_NOT_READY,VK_ERROR_OUT_OF_DATE_KHR};
    assert(s.AcquireNextImage() && s.is_outdated);
    assert(s.scheduler.waits==0 && s.device.logical.calls==2);
  }
#endif
  {
    Swapchain s;
    s.device.logical.results={VK_ERROR_SURFACE_LOST_KHR};
    bool error=false;
    try{(void)s.AcquireNextImage();}catch(const vk::Exception& e){
      error=e.GetResult()==VK_ERROR_SURFACE_LOST_KHR;
    }
    assert(error);
    assert(s.scheduler.waits==0);
  }
  std::puts("PASS: source generated WSI native path handles success, outdated, retry, terminal timeout");
}
""".replace("__REAL_METHOD__",body)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-ps5-vk-acquire-") as tmp:
    source=Path(tmp)/"acquire.cpp"
    source.write_text(stub)
    for native in (False,True):
        exe=Path(tmp)/("native" if native else "portable")
        argv=[compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror"]
        if native:argv.append("-DPS5_NATIVE")
        subprocess.run(argv+[str(source),"-o",str(exe)],check=True,timeout=60)
        x=subprocess.run([str(exe)],capture_output=True,text=True,timeout=8)
        assert x.returncode==0,(native,x.stderr)
        print(("NATIVE" if native else "PORTABLE"),x.stdout.strip())
print("HOST SOURCE REPLAY: actual Vulkan driver, swapchain count, monitor and title not emulated")
