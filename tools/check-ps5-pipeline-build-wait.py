#!/usr/bin/env python3
"""R378: source-extracted Vulkan worker completion, no indefinite pipeline wait."""
from pathlib import Path
import os,subprocess,sys,tempfile

root=Path(__file__).resolve().parents[1]
paths=[
    root/'vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp',
    root/'vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp',
]
generator=(root/'tools/prepare-vulkan-port.py').read_text()
guards=[]
for path in paths:
    data=path.read_text()
    assert '#include "common/scope_exit.h"' in data,path
    start=data.index("        SCOPE_EXIT {",data.index("    auto func{[this, shader_notify"))
    stop=data.index("        };",start)+len("        };")
    guard=data[start:stop]
    assert "is_built.store(true, std::memory_order_release)" in guard
    assert "build_condvar.notify_all()" in guard
    assert "shader_notify->MarkShaderComplete()" in guard
    assert "std::scoped_lock lock{build_mutex}" in guard
    assert data.count("build_condvar.notify_all()")==1
    assert data.count("build_condvar.notify_one()")==0
    assert 'catch (const std::exception& exception)' in data
    assert 'catch (...)' in data
    assert "if (pipeline_statistics && pipeline)" in data
    guards.append(guard)
assert "build_condvar.notify_all()" in generator
assert '"common/scope_exit.h"' in generator

model=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <stdexcept>
#include <thread>
#include "common/scope_exit.h"

struct Notify {
    std::atomic<int> completes{};
    void MarkShaderComplete() noexcept {
        completes.fetch_add(1,std::memory_order_relaxed);
    }
};
struct Worker {
    std::mutex build_mutex;
    std::condition_variable build_condvar;
    std::atomic_bool is_built{false};
    void Build(int kind, Notify* shader_notify) {
__SOURCE_GUARD__
        try {
            if (kind==1) throw std::runtime_error("Vulkan/resource exception");
            if (kind==2) throw 42;  // non-std exception
            if (kind==3) return;    // unexpected early exit
        } catch (const std::exception&) {
        } catch (...) {
        }
    }
};
int main() {
    for(int kind=0;kind<4;++kind) {
        Worker p;
        Notify notify;
        std::atomic_bool released{false};
        std::thread waiter([&] {
            std::unique_lock lock{p.build_mutex};
            const bool ok=p.build_condvar.wait_for(
                lock,std::chrono::seconds(2),
                [&] {return p.is_built.load(std::memory_order_acquire);});
            released.store(ok,std::memory_order_release);
        });
        std::thread worker([&] {p.Build(kind,&notify);});
        worker.join();waiter.join();
        assert(released.load(std::memory_order_acquire));
        assert(p.is_built.load(std::memory_order_acquire));
        assert(notify.completes.load()==1);
    }
    Worker no_notifier;
    no_notifier.Build(2,nullptr);
    assert(no_notifier.is_built.load());
}
"""
env=os.environ.copy()
if sys.platform=='darwin' and not env.get('SDKROOT'):
    sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
    if sdk.is_dir():env['SDKROOT']=str(sdk)
include=root/'vendor/sources/eden/src'
with tempfile.TemporaryDirectory(prefix='eden-r378-pipeline-') as td:
    for n,guard in enumerate(guards):
        code=model.replace('__SOURCE_GUARD__',guard)
        source=Path(td)/f'worker{n}.cpp'
        exe=Path(td)/f'worker{n}'
        source.write_text(code)
        subprocess.run(['c++','-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-I',str(include),
                        str(source),'-o',str(exe)],check=True,env=env,timeout=35)
        subprocess.run([str(exe)],check=True,env=env,timeout=25)
print('PASS R378 actual GRAPHICS and COMPUTE SCOPE_EXIT: success, std/foreign exception, early return, notify exactly once')
