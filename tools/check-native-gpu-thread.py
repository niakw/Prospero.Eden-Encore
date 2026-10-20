#!/usr/bin/env python3
"""Exercise the actual native lifecycle and verify the generated worker body is preserved."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
cache = Path((root / '.local/headless-cache').read_text().strip())
upstream = cache / 'source/src'
generated = cache / 'native-local/headless/gpu_thread.cpp'
source = (upstream / 'video_core/gpu_thread.cpp').read_text()
worker = generated.read_text()
body = source.split('thread = std::jthread([&](std::stop_token stop_token) {', 1)[1].split('\n    });', 1)[0]
dispatch_call = '                scheduler.Push(system.GPU(), submit_list->channel, std::move(submit_list->entries));'
development = 'EDEN_DEV_PROFILE:BOOL=ON' in (cache / 'native-local/CMakeCache.txt').read_text()
for call, timer, indent in (
    (dispatch_call, 'dispatch_timer(::Eden::Performance::gpu_dispatch)', '                '),
    ('            state.queue.PopWait(next, stop_token);',
     'idle_timer(::Eden::Performance::gpu_queue_wait)', '            '),
):
    wrapped = indent + '{ ::Eden::Performance::DiagnosticTimer ' + timer + ';\n' + call + '\n' + indent + '}'
    assert worker.count(wrapped) == int(development)
    worker = worker.replace(wrapped, call)

trace_when = 'count <= 3 || ::Eden::Performance::BootTrace()' if development else 'count <= 3'
dispatch_trace = ('                const auto count = ++dispatches;\n'
                  f'                if ({trace_when}) LOG_INFO(Render_OpenGL, "EDEN_GPU_DISPATCH_BEGIN count={{}}", count);\n'
                  + dispatch_call + '\n'
                  f'                if ({trace_when}) LOG_INFO(Render_OpenGL, "EDEN_GPU_DISPATCH_END count={{}}", count);')
assert worker.count(dispatch_trace) == 1
untraced = worker.replace(dispatch_trace, dispatch_call).replace('        unsigned dispatches = 0;\n', '')
# R293 diagnostic-only timers wrap the other three GPU worker command types.
# Restore original calls when comparing the generated worker to pinned Eden.
for metric, call in (
    ('gpu_command_tick', '                system.GPU().TickWork();'),
    ('gpu_command_flush', '                renderer.ReadRasterizer()->FlushRegion(flush->addr, flush->size);'),
    ('gpu_command_invalidate',
     '                renderer.ReadRasterizer()->OnCacheInvalidation(invalidate->addr, invalidate->size);'),
):
    wrapped = ('                { ::Eden::Performance::DiagnosticTimer category_timer('
               '::Eden::Performance::' + metric + ');\n' + call + '\n                }')
    assert untraced.count(wrapped) == int(development)
    untraced = untraced.replace(wrapped, call)
# The producer is outside the upstream worker body. Compare its complete
# compiled TU to the selected maintained source, including failure propagation
# and acquire loads, rather than normalizing an obsolete relaxed-load fragment.
profile = 'dev' if development else 'quiet'
maintained_worker = root / f'vendor/encore-active/eden-gpu/gpu_thread_{profile}.cpp'
assert generated.read_bytes() == maintained_worker.read_bytes()
producer = worker.split('u64 ThreadManager::PushCommand(', 1)[1].split('\n} // namespace', 1)[0]
assert producer.count('TryEmplace(') == 1
assert producer.count('EmplaceWaitWithStopToken(') == 1
assert producer.count('Eden::PeekGpuFailure()') == 2
assert 'std::memory_order_relaxed' not in producer
loading_wait = """            if (Eden::LoadingTick(renderer, false)) {
                if (!state.queue.TryPop(next)) {
                    Eden::LoadingTick(renderer, true);
                    std::this_thread::sleep_for(std::chrono::milliseconds(1));
                    continue;
                }
            } else {
            state.queue.PopWait(next, stop_token);
            }"""
assert untraced.count(loading_wait) == 1
untraced = untraced.replace(loading_wait, '            state.queue.PopWait(next, stop_token);')
# The native crash-only breadcrumb is coarse (one relaxed atomic per 64
# completed GPU commands); strip it solely for the upstream-body comparison.
progress_marker = (
    '            // Release publishes completed GPU work to acquire-side fence readers.\n'
    '            state.signaled_fence.store(next.fence, std::memory_order_release);\n'
    '            if ((++completed_gpu_commands & 63u) == 0u)\n'
    '                ::Eden::Crash::gpu_completed_commands.fetch_add(64, std::memory_order_relaxed);'
)
assert untraced.count(progress_marker) == 1
# Normalize the maintained release-store fast path to the pinned seq_cst
# publication only for this legacy full-body parity oracle. The separate
# source-extracted concurrency fixture verifies its acquire/release protocol.
untraced = untraced.replace(progress_marker, '            state.signaled_fence.store(next.fence);')
assert untraced.count('        unsigned completed_gpu_commands = 0;\n') == 1
untraced = untraced.replace('        unsigned completed_gpu_commands = 0;\n', '')
assert body in untraced, 'GPU worker semantics changed beyond dispatch markers and startup animation wait'

assert 'stop_source.get_token()' in worker and 'thread.get_stop_token()' not in worker
assert 'ThreadManager::~ThreadManager() { Stop(); }' in worker
gpu = (root / 'vendor/encore-active/eden-core/src' / ('video_core/gpu_gl_native_dev.cpp' if development else 'video_core/gpu_gl_native.cpp')).read_text()
assert 'GPU::~GPU() { impl->NotifyShutdown(); }' in gpu
shutdown = gpu.split('    void NotifyShutdown() {', 1)[1].split('    /// Obtain', 1)[0]
assert 'sync_cv.notify_all();\n        }\n        gpu_thread.Stop();' in shutdown
assert shutdown.index('gpu_thread.Stop();') < shutdown.index('sync_requests.clear();') < shutdown.index('sync_requests_stopped = true;')
assert '~Impl() { gpu_thread.Stop(); if (renderer && Settings::IsOpenGL()) { renderer->Context().MakeCurrent(); glFinish(); } }' in gpu
core = (cache / 'native-local/headless/core.cpp').read_text()
shutdown_core = core.split('    void ShutdownMainProcess() {', 1)[1].split('    bool IsShuttingDown()', 1)[0]
assert shutdown_core.index('gpu_core->NotifyShutdown()') < shutdown_core.index('services.reset()') < shutdown_core.index('gpu_core.reset()')
if sys.platform == 'darwin':
    # The behavioral harness below validates the Linux pthread stack with
    # pthread_getattr_np. All generated native GPU shutdown/stop/join ordering
    # assertions above still run on macOS; the real implementation is compiled
    # for PS5 by the native target and the pthread runtime harness stays in CI.
    print('Native GPU generated lifecycle/ordering contract PASS (Linux pthread runtime harness deferred to CI)')
    raise SystemExit(0)
code = r'''
#include "gpu_failure.h"
#include "diagnostics.h"
#include <cstdio>
#include <mutex>
#include <string>
#include <cassert>
#include <cerrno>
#include <memory>
#include <pthread.h>
#include <semaphore>
#include <stop_token>
#include <system_error>
#include <functional>
#include <thread>
#include "common/bounded_threadsafe_queue.h"
static int fault, attributes_live, joins;
static std::binary_semaphore* joining;
static int init(pthread_attr_t* a) {
    if (fault == 1) return ENOMEM;
    int result = pthread_attr_init(a); if (!result) ++attributes_live; return result;
}
static int stack(pthread_attr_t* a, size_t size) {
    assert(size == 1024 * 1024);
    return fault == 2 ? EINVAL : pthread_attr_setstacksize(a, size);
}
static int destroy(pthread_attr_t* a) { --attributes_live; return pthread_attr_destroy(a); }
static int create(pthread_t* t, const pthread_attr_t* a, void* (*f)(void*), void* p) {
    return fault == 3 ? EAGAIN : pthread_create(t, a, f, p);
}
static int join(pthread_t t, void** out) {
    ++joins;
    if (joining) joining->release();
    return pthread_join(t, out);
}
namespace VideoCore { struct RendererBase { void* ReadRasterizer() { return this; } }; }
namespace Core::Frontend { struct GraphicsContext {}; }
namespace Tegra::Control { struct Scheduler {}; }
namespace VideoCommon::GPUThread {
class ThreadManager {
public:
    ~ThreadManager() { Stop(); }
    void StartThread(VideoCore::RendererBase&, Core::Frontend::GraphicsContext&, Tegra::Control::Scheduler&);
    void Stop();
    using CommandDataContainer = int;
    struct { std::mutex write_lock; Common::SPSCQueue<int, 4> queue; } state;
    std::binary_semaphore ready{0};
    bool finished{};
    std::function<void()> command;
private:
    void RunWorker(VideoCore::RendererBase&, Core::Frontend::GraphicsContext&, Tegra::Control::Scheduler&) {
        pthread_attr_t a;
        assert(pthread_getattr_np(pthread_self(), &a) == 0);
        size_t size;
        assert(pthread_attr_getstacksize(&a, &size) == 0 && size == 1024 * 1024);
        assert(pthread_attr_destroy(&a) == 0);
        int value = 0;
        state.queue.PopWait(value, stop_source.get_token());
        assert(value == 42 && !stop_source.stop_requested());
        if (command) { command(); finished = true; return; }
        ready.release();
        state.queue.PopWait(value, stop_source.get_token());
        assert(stop_source.stop_requested());
        finished = true;
    }
    void* rasterizer{};
    pthread_t thread{};
    std::stop_source stop_source;
    bool thread_joinable{};
};
}
#define pthread_attr_init init
#define pthread_attr_setstacksize stack
#define pthread_attr_destroy destroy
#define pthread_create create
#define pthread_join join
LIFECYCLE
int main(int argc, char**) {
    VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;
    Tegra::Control::Scheduler scheduler;
    using VideoCommon::GPUThread::ThreadManager;
    if (argc > 1) {
        ThreadManager manager;
        manager.command = [&] { manager.ready.release(); throw std::runtime_error("injected worker failure"); };
        manager.StartThread(renderer, context, scheduler);
        manager.state.queue.EmplaceWait(42);
        manager.ready.acquire();
        manager.Stop();
        assert(Eden::PeekGpuFailure());
        assert(Eden::TakeGpuFailure());
        assert(Eden::PeekGpuFailure() && !Eden::TakeGpuFailure());
        try { std::rethrow_exception(Eden::PeekGpuFailure()); }
        catch (const std::runtime_error& error) {
            assert(std::string(error.what()) == "injected worker failure");
            return 0;
        }
        return 1;
    }
    for (fault = 1; fault <= 3; ++fault) {
        ThreadManager manager;
        try { manager.StartThread(renderer, context, scheduler); assert(false); }
        catch (const std::system_error&) {}
        assert(attributes_live == 0 && joins == 0);
    }
    fault = 0;
    ThreadManager manager;
    for (int i = 1; i <= 3; ++i) {
        manager.finished = false;
        manager.state.queue.EmplaceWait(7);
        manager.StartThread(renderer, context, scheduler);
        manager.state.queue.EmplaceWait(42);
        manager.ready.acquire();
        manager.Stop();
        manager.Stop();
        assert(manager.finished && joins == i && attributes_live == 0);
    }
    { ThreadManager implicit;
      implicit.StartThread(renderer, context, scheduler);
      implicit.state.queue.EmplaceWait(42);
      implicit.ready.acquire(); }
    assert(joins == 4 && attributes_live == 0);
    // A command already executing must exit before the protected owner goes.
    // Old ordering deterministically exposes the cleared unique_ptr, without
    // dereferencing it or relying on a scheduling delay.
    for (bool early_join : {false, true}) {
        std::binary_semaphore entered{0}, release{0}, join_started{0};
        bool pointer_alive = false, owner_destroyed = false;
        struct Protected {
            ThreadManager worker;
            bool& destroyed;
            explicit Protected(bool& flag) : destroyed(flag) {}
            ~Protected() { worker.Stop(); destroyed = true; }
        };
        auto owner = std::make_unique<Protected>(owner_destroyed);
        owner->worker.command = [&] {
            entered.release();
            release.acquire();
            pointer_alive = owner != nullptr && !owner_destroyed;
        };
        owner->worker.StartThread(renderer, context, scheduler);
        owner->worker.state.queue.EmplaceWait(42);
        entered.acquire();
        joining = &join_started;
        std::thread teardown([&] {
            if (early_join) owner->worker.Stop();
            owner.reset();
        });
        join_started.acquire();
        assert(!owner_destroyed);
        release.release();
        teardown.join();
        joining = nullptr;
        assert(owner_destroyed && pointer_alive == early_join);
    }
}
'''
lifecycle = worker.split('// PS5-only ThreadManager lifecycle;', 1)[1]
lifecycle = lifecycle[lifecycle.index('namespace VideoCommon::GPUThread {'):]
code = code.replace('LIFECYCLE', lifecycle)
with tempfile.TemporaryDirectory(prefix='eden-gpu-thread-') as folder:
    temp = Path(folder)
    (temp / 'check.cpp').write_text(code)
    subprocess.run(['c++', '-std=c++20', '-pthread', '-Wall', '-Wextra', '-Werror',
                    '-I', str(upstream), '-I', str(root / 'headless'), str(temp / 'check.cpp'),
                    '-o', str(temp / 'check')], check=True)
    subprocess.run([str(temp / 'check')], check=True, timeout=15)
    failed = subprocess.run([str(temp / 'check'), 'throw'], capture_output=True, text=True, timeout=15)
    assert failed.returncode == 0 and '[ProsperoEden] GPU worker: injected worker failure' in failed.stderr
print('Native GPU stack, stop/wake/join, creation failures and blocked-command teardown ordering/rejection PASS')
