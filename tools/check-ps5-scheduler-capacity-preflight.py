#!/usr/bin/env python3
"""R382: source-extracted scheduler command capacity preflight and lock-order test."""
from pathlib import Path
import os, subprocess, sys, tempfile

root=Path(__file__).resolve().parents[1]
header=(root/'vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_scheduler.h').read_text()
raster=(root/'vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp').read_text()
generator=(root/'tools/prepare-vulkan-port.py').read_text()
a=header.index('    bool PreflightDrawCommands() {')
b=header.index('\n    }\n#endif',a)+len('\n    }')
preflight=header[a:b]
a=header.index('        bool HasReserve(size_t bytes) const noexcept {')
b=header.index('\n        }\n#endif',a)+len('\n        }')
capacity=header[a:b]
assert preflight.count('DispatchWork();')==1
assert 'constexpr size_t kDrawCommandReserve = 4096;' in preflight
assert 'chunk->Empty()' in preflight and 'chunk->HasReserve(kDrawCommandReserve)' in preflight
assert 'alignof(std::max_align_t)' in capacity
assert 'command_offset <= data.size() - needed' in capacity
assert 'RecordWithUploadBuffer' in header and 'DispatchWork();' in header
assert 'PreflightDrawCommands' in generator
assert raster.count('scheduler.PreflightDrawCommands();') == 2
assert raster.index('scheduler.PreflightDrawCommands();') < raster.index('std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};')
block=raster[raster.index('void RasterizerVulkan::DispatchCompute() {'):]
assert block.index('scheduler.PreflightDrawCommands();') < block.index('std::scoped_lock lock{texture_cache.mutex, buffer_cache.mutex};')
assert raster.index('scheduler.PreflightDrawCommands();') < raster.index('gpu_memory->FlushCaching();')
assert block.index('scheduler.PreflightDrawCommands();') < block.index('gpu_memory->FlushCaching();')
code=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <memory>
class Scheduler {
public:
    class CommandChunk {
    public:
        std::size_t command_offset{};
        std::array<std::uint8_t,0x8000> data{};
        bool Empty() const {return command_offset==0;}
__HAS_RESERVE__
    };
    std::unique_ptr<CommandChunk> chunk{std::make_unique<CommandChunk>()};
    unsigned sent{};
    unsigned fence_waits{};
    void DispatchWork() {
        assert(!chunk->Empty());
        ++sent;
        chunk=std::make_unique<CommandChunk>();
    }
__PREFLIGHT__
};
int main() {
    Scheduler scheduler;
    assert(!scheduler.PreflightDrawCommands());
    assert(scheduler.sent==0 && scheduler.fence_waits==0);
    scheduler.chunk->command_offset=0x4000;
    assert(!scheduler.PreflightDrawCommands());
    assert(scheduler.sent==0);
    const auto boundary = scheduler.chunk->data.size() - 4096 - alignof(std::max_align_t);
    scheduler.chunk->command_offset=boundary;
    assert(!scheduler.PreflightDrawCommands());
    scheduler.chunk->command_offset=boundary + 1;
    assert(scheduler.PreflightDrawCommands());
    assert(scheduler.sent==1 && scheduler.chunk->Empty());
    assert(scheduler.fence_waits==0);
    assert(!scheduler.PreflightDrawCommands());
    scheduler.chunk->command_offset=0x7000;
    assert(scheduler.PreflightDrawCommands());
    assert(scheduler.sent==2);
    assert(scheduler.chunk->HasReserve(4096));
    assert(!scheduler.chunk->HasReserve(0x8000));
    scheduler.chunk->command_offset=0x7fff;
    assert(!scheduler.chunk->HasReserve(4096));
    assert(scheduler.PreflightDrawCommands());
    assert(scheduler.sent==3 && scheduler.fence_waits==0);
}
""".replace('__HAS_RESERVE__',capacity).replace('__PREFLIGHT__',preflight)
env=os.environ.copy()
if sys.platform=='darwin' and not env.get('SDKROOT'):
    sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
    if sdk.exists():env['SDKROOT']=str(sdk)
with tempfile.TemporaryDirectory(prefix='eden-r382-command-') as td:
    source=Path(td)/'capacity.cpp'
    exe=Path(td)/'capacity'
    source.write_text(code)
    subprocess.run(['c++','-std=c++20','-O1','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined',str(source),'-o',str(exe)],
                   check=True,env=env,timeout=30)
    subprocess.run([str(exe)],check=True,env=env,timeout=15)
print('PASS R382 native scheduler preflight: 4KiB spare boundary, no empty dispatch, no GPU waits, outside cache locks')
