#!/usr/bin/env python3
"""F07 P0.3: execute selected Vulkan compute-indirect command path on the host.

The source fragment is taken verbatim from active DispatchCompute. In PS5 mode
an absent guest buffer must return before recording barriers or using Handle().
Valid buffers, existing compute barriers, and desktop semantics are preserved.
No actual PS5 Vulkan device, guest compute program, or FC27 is emulated.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp"
active = path.read_text()
generator = (ROOT / "tools/prepare-vulkan-port.py").read_text()
pinned = (ROOT / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp")
fast = (ROOT / ".github/workflows/encore-core-fast-gate.yml").read_text()
preflight = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
invocation = "python3 -B tools/check-ps5-f07-compute-indirect-binding-host.py"
assert invocation in fast and invocation in preflight
assert "F07 reject unmapped indirect compute buffer before Vulkan commands" in generator
assert "F07 compute indirect reject null Vulkan handles" in generator

method_start = "void RasterizerVulkan::DispatchCompute() {"
method_end = "\n}\n"
assert active.count(method_start) == 1
start = active.index(method_start)
end = active.index(method_end, start)
method = active[start:end]
branch_start = "    if (indirect_address) {\n"
branch_end = "    const std::array<u32, 3> dim{"
assert method.count(branch_start) == method.count(branch_end) == 1
chunk = method[method.index(branch_start):method.index(branch_end)]
assert chunk.count("buffer_cache.ObtainBuffer(*indirect_address, 12, sync_info, post_op)") == 1
assert chunk.count("if (!buffer || buffer->Handle() == VK_NULL_HANDLE) {") == 1
assert chunk.count("scheduler.RequestOutsideRenderPassOperationContext();") == 1
assert chunk.count("indirect_buffer = buffer->Handle()") == 1
assert chunk.index("if (!buffer || buffer->Handle() == VK_NULL_HANDLE) {") < chunk.index("scheduler.RequestOutsideRenderPassOperationContext();")
assert chunk.index("scheduler.RequestOutsideRenderPassOperationContext();") < chunk.index("indirect_buffer = buffer->Handle()")
assert "#ifdef PS5_NATIVE\n        // A guest indirect-command address" in chunk
assert "#endif\n        scheduler.RequestOutsideRenderPassOperationContext();" in chunk

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <utility>
namespace VideoCommon {
enum class ObtainBufferSynchronize { FullSynchronize };
enum class ObtainBufferOperation { DiscardWrite };
}
namespace Eden::DevVulkan { inline bool compute_barriers = false; }
inline constexpr int VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT=1;
inline constexpr int VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT=2;
inline constexpr int COMPUTE_INPUT_BARRIER=3;
inline constexpr int COMPUTE_CONSUMER_STAGES=4;
inline constexpr int COMPUTE_WRITE_BARRIER=5;
struct Counters {
    unsigned contexts{}, records{}, dispatches{}, barriers{};
    int handle{};
    std::size_t offset{};
};
namespace vk {
inline constexpr int PIPELINE_STAGE_GRAPHICS_COMPUTE_TRANSFER=6;
struct CommandBuffer {
    Counters* events{};
    void PipelineBarrier(int,int,int,int){++events->barriers;}
    void DispatchIndirect(int handle, std::size_t offset) {
        ++events->dispatches;
        events->handle=handle;
        events->offset=offset;
    }
};
}
inline constexpr int VK_NULL_HANDLE=0;
struct Buffer {int value{91};int Handle() const {return value;}};
struct BufferCache {
    Buffer* active{};
    std::pair<Buffer*,std::size_t> ObtainBuffer(
        std::uint64_t address,std::size_t size,
        VideoCommon::ObtainBufferSynchronize,
        VideoCommon::ObtainBufferOperation) {
        assert(address==48 && size==12);
        return {active,24};
    }
};
struct Pipeline {
    bool bound{true};
    bool IsBound() const {return bound;}
};
struct Scheduler {
    Counters events{};
    void RequestOutsideRenderPassOperationContext(){++events.contexts;}
    template<class Fn> void Record(Fn fn) {
        ++events.records;
        fn(vk::CommandBuffer{&events});
    }
};
struct Cache {
    Buffer storage{};
    BufferCache buffer_cache{&storage};
    Pipeline pipe{};
    Scheduler scheduler{};
    bool mapped{true};
    void Dispatch() {
        buffer_cache.active=mapped ? &storage : nullptr;
        auto* pipeline=&pipe;
        const std::optional<std::uint64_t> indirect_address{48};
__EXTRACTED_BRANCH__
        assert(false && "indirect compute unexpectedly fell through");
    }
};
int main(){
#ifdef PS5_NATIVE
    Cache missing;
    missing.mapped=false;
    missing.Dispatch();
    assert(missing.scheduler.events.contexts==0);
    assert(missing.scheduler.events.records==0);
    assert(missing.scheduler.events.dispatches==0);
    Cache missing_vk;
    missing_vk.storage.value=VK_NULL_HANDLE;
    missing_vk.Dispatch();
    assert(missing_vk.scheduler.events.contexts==0);
    assert(missing_vk.scheduler.events.records==0);
    assert(missing_vk.scheduler.events.dispatches==0);
#endif
    Cache valid;
    valid.Dispatch();
    assert(valid.scheduler.events.contexts==1);
    assert(valid.scheduler.events.records==1);
    assert(valid.scheduler.events.dispatches==1);
    assert(valid.scheduler.events.barriers==0);
    assert(valid.scheduler.events.handle==91);
    assert(valid.scheduler.events.offset==24);

    Eden::DevVulkan::compute_barriers=true;
    Cache with_barriers;
    with_barriers.Dispatch();
    assert(with_barriers.scheduler.events.contexts==1);
    assert(with_barriers.scheduler.events.records==2);
    assert(with_barriers.scheduler.events.dispatches==1);
    assert(with_barriers.scheduler.events.barriers==2);

    Cache not_bound;
    not_bound.pipe.bound=false;
    not_bound.Dispatch();
    assert(not_bound.scheduler.events.records==2);
    assert(not_bound.scheduler.events.dispatches==0);
    Eden::DevVulkan::compute_barriers=false;
}
""".replace("__EXTRACTED_BRANCH__",chunk)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "F07 compute indirect test requires C++20 compiler"
with tempfile.TemporaryDirectory(prefix="eden-f07-indirect-compute-") as directory:
    source=Path(directory)/"indirect.cpp"
    source.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            exe=Path(directory)/("indirect"+opt[1:]+("-ps5" if native else "-desktop"))
            built=subprocess.run(
                [compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),str(source),"-o",str(exe)],
                capture_output=True,text=True,timeout=45)
            assert built.returncode==0,(native,opt,built.stderr[-6500:])
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert ran.returncode==0,(native,opt,ran.stderr[-5000:])
print("F07_COMPUTE_INDIRECT_BINDING_PASS native_null_reject=1 native_null_vk_reject=1 no_barrier_on_null=1 valid_dispatch=1 full_barriers=1 unbound_pipeline=1 desktop_original=1 O0=1 O2=1")
