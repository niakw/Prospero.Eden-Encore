#!/usr/bin/env python3
"""R381: source-backed Vulkan draw guard after async pipeline failure."""
from pathlib import Path
import os, subprocess, sys, tempfile

root=Path(__file__).resolve().parents[1]
header=(root/'vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h').read_text()
raster=(root/'vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp').read_text()
generator=(root/'tools/prepare-vulkan-port.py').read_text()
pipeline_cpp=(root/'vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp').read_text()
start=header.index('    [[nodiscard]] bool CanExecuteDraw() const noexcept {')
end=header.index('\n    }',start)+len('\n    }')
method=header[start:end]
assert 'is_built.load(std::memory_order::acquire)' in method
assert 'static_cast<bool>(pipeline)' in method
assert "CanExecuteDraw()" in generator
assert 'build_condvar.wait(lock' in pipeline_cpp
assert 'scheduler.Record([this](vk::CommandBuffer)' in pipeline_cpp
assert raster.count("pipeline = prepared_pipeline](vk::CommandBuffer cmdbuf)")==4
assert raster.count("if (!pipeline || !pipeline->CanExecuteDraw()) {")==4
assert raster.count("::Eden::Performance::GraphicsDrawDrop::WorkerPipelineFailed);") >= 4
# Guard must precede the first Vulkan draw command of each queue record.
for name in ("Draw(", "DrawIndirectByteCountEXT(", "DrawIndexedIndirectCount(", "DrawIndexedIndirect("):
    # Each variant is constructed from its own scheduler.Record capture.
    index=raster.index("cmdbuf."+name)
    preceding=raster[:index].rfind("scheduler.Record([")
    relevant=raster[preceding:index]
    assert "pipeline = prepared_pipeline" in relevant, name
    assert "pipeline->CanExecuteDraw()" in relevant, name
    assert relevant.index("pipeline->CanExecuteDraw()") < relevant.index("return;"), name
guard='''            if (!pipeline || !pipeline->CanExecuteDraw()) {
                ::Eden::Performance::RecordGraphicsDrawDrop(
                    ::Eden::Performance::GraphicsDrawDrop::WorkerPipelineFailed);
                return;
            }'''
assert guard in raster
program = r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <mutex>
#include <condition_variable>
#include <thread>
namespace Eden::Performance {
enum class GraphicsDrawDrop { WorkerPipelineFailed };
inline std::atomic<int> dropped{0};
void RecordGraphicsDrawDrop(GraphicsDrawDrop) { dropped.fetch_add(1); }
}
struct Pipeline {
    std::atomic<bool> is_built{false};
    bool pipeline{};
__REAL_READY_METHOD__
};
using GraphicsPipeline = Pipeline;
void worker_record(GraphicsPipeline* pipeline, int& count) {
__REAL_FAIL_GUARD__
    ++count;
}
int main() {
    int draws=0;
    Pipeline failed;
    // Four queued call sites: draw, indirect byte-count, indirect count,
    // and indirect direct (indexed or nonindexed).
    for(int i=0;i<4;++i)worker_record(nullptr,draws);
    for(int i=0;i<4;++i)worker_record(&failed,draws);
    failed.is_built.store(true,std::memory_order_release);
    for(int i=0;i<4;++i)worker_record(&failed,draws);
    assert(draws==0 && Eden::Performance::dropped.load()==12);
    Pipeline ok;
    std::mutex m;
    std::condition_variable cv;
    std::thread waiter([&]{
        std::unique_lock lock(m);
        cv.wait(lock,[&]{return ok.is_built.load(std::memory_order::acquire);});
        for(int i=0;i<4;++i)worker_record(&ok,draws);
    });
    std::thread creator([&]{
        ok.pipeline=true;
        ok.is_built.store(true,std::memory_order_release);
        cv.notify_all();
    });
    waiter.join();creator.join();
    assert(draws==4 && Eden::Performance::dropped.load()==12);
}
""".replace('__REAL_READY_METHOD__',method).replace('__REAL_FAIL_GUARD__',guard)
env=os.environ.copy()
if sys.platform=='darwin' and not env.get('SDKROOT'):
    sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
    if sdk.is_dir():env['SDKROOT']=str(sdk)
with tempfile.TemporaryDirectory(prefix='eden-r381-guard-') as d:
    cpp=Path(d)/'guard.cpp';exe=Path(d)/'guard'
    cpp.write_text(program)
    subprocess.run(['c++','-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined',str(cpp),'-o',str(exe)],
                   check=True,env=env,timeout=35)
    subprocess.run([str(exe)],check=True,env=env,timeout=15)
print('PASS R381: 4 queued draw variants reject failed pipeline; success paths execute; release/acquire validated')
