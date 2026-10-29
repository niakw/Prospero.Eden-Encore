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
general_method=header[start:end]
recorded_start=header.index('    [[nodiscard]] bool CanExecuteRecordedDraw() const noexcept {')
recorded_end=header.index('\n    }',recorded_start)+len('\n    }')
recorded_method=header[recorded_start:recorded_end]
method=general_method+'\n'+recorded_method
assert 'is_built.load(std::memory_order::acquire)' in method
assert 'static_cast<bool>(pipeline)' in method
assert "CanExecuteDraw()" in generator
assert 'build_condvar.wait(lock' in pipeline_cpp
assert 'scheduler.Record([this](vk::CommandBuffer)' in pipeline_cpp
assert raster.count("pipeline = prepared_pipeline](vk::CommandBuffer cmdbuf)")==4
assert raster.count("if (!pipeline || !pipeline->CanExecuteRecordedDraw()) {")==4
assert "return worker_draw_bind_valid;" in recorded_method
assert "return CanExecuteDraw();" in recorded_method
assert "CanExecuteRecordedDraw()" in generator
assert raster.count("::Eden::Performance::GraphicsDrawDrop::WorkerPipelineFailed);") >= 4
# Guard must precede the first Vulkan draw command of each queue record.
for name in ("Draw(", "DrawIndirectByteCountEXT(", "DrawIndexedIndirectCount(", "DrawIndexedIndirect("):
    # Each variant is constructed from its own scheduler.Record capture.
    index=raster.index("cmdbuf."+name)
    preceding=raster[:index].rfind("scheduler.Record([")
    relevant=raster[preceding:index]
    assert "pipeline = prepared_pipeline" in relevant, name
    assert "pipeline->CanExecuteRecordedDraw()" in relevant, name
    assert relevant.index("pipeline->CanExecuteRecordedDraw()") < relevant.index("return;"), name
guard='''            if (!pipeline || !pipeline->CanExecuteRecordedDraw()) {
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
    std::atomic_bool optimized_ready{false};
#ifdef PS5_NATIVE
    bool worker_draw_bind_valid{};
#endif
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
        // Publish under the same mutex as cv.wait. Without this lock,
        // notify_all() may precede the waiter's actual sleep even though
        // its predicate is atomic, causing an intermittent host-test hang.
        {
            std::lock_guard lock(m);
            ok.pipeline=true;
#ifdef PS5_NATIVE
            ok.worker_draw_bind_valid=true;
#endif
            ok.is_built.store(true,std::memory_order_release);
        }
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
    for mode in ('native', 'desktop'):
        target=Path(d)/('guard-'+mode)
        flags=['-DPS5_NATIVE=1'] if mode=='native' else []
        subprocess.run(['c++','-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined',*flags,str(cpp),'-o',str(target)],
                       check=True,env=env,timeout=35)
        subprocess.run([str(target)],check=True,env=env,timeout=15)
print('PASS R381: 4 queued draw variants reject failed pipeline; success paths execute; release/acquire validated')
