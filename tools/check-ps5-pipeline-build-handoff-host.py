#!/usr/bin/env python3
"""Verify selected Vulkan first-use shader completion ownership.

Extracts the actual early-construction RAII guard from the maintained C++
constructor. Host scenarios cover setup failures, queue failures, synchronous
and asynchronous worker completion. This is a source-contract/host proof only,
not a complete native pipeline compilation or a PS5 frame-time result.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
begin = source.index("GraphicsPipeline::GraphicsPipeline(")
end = source.index("\nvoid GraphicsPipeline::AddTransition(", begin)
ctor = source[begin:end]

mark = """    if (shader_notify) {
        shader_notify->MarkShaderBuilding();
    }
"""
guard_begin = ctor.index("    bool build_handed_off = false;")
guard_end = ctor.index("    for (size_t stage = 0;", guard_begin)
guard = ctor[guard_begin:guard_end]
assert ctor.count(mark) == 1
assert "SCOPE_EXIT {" in guard
assert "if (!build_handed_off && shader_notify)" in guard
assert "shader_notify->MarkShaderComplete();" in guard
assert ctor.count("build_handed_off = true;") == 2
assert ctor.index("configure_func = ConfigureFunc(spv_modules, stage_infos);") < (
    ctor.index("worker_thread->QueueWork(")
)
assert ctor.index("configure_func = ConfigureFunc(spv_modules, stage_infos);") < (
    ctor.index("    if (worker_thread) {")
)
assert ctor.index("build_handed_off = true;") > ctor.index("worker_thread->QueueWork(")
assert ctor.index("build_handed_off = true;") < ctor.index("    } else {\n        // Synchronous func()")

# The exact real guard, including its destructor lambda, is compiled. Only
# descriptor preparation and worker queue ownership are stand-ins.
host = r"""
#include <cassert>
#include <cstdio>
#include <functional>
#include <stdexcept>
#include <type_traits>
#include <utility>
struct Maker {};
template<class F> struct ScopeGuard {
    F f;
    ~ScopeGuard() { f(); }
};
template<class F> ScopeGuard<std::decay_t<F>> operator+(Maker, F&& f) {
    return {std::forward<F>(f)};
}
#define SCOPE_EXIT auto _guard = Maker{} + [&]
struct Notify {
    int building{}, complete{}, outstanding{};
    void MarkShaderBuilding() { ++building; ++outstanding; }
    void MarkShaderComplete() {
        ++complete;
        --outstanding;
        assert(outstanding >= 0);
    }
};
struct Queue {
    std::function<void()> work;
    bool fail{};
    void QueueWork(std::function<void()> job) {
        if (fail) throw std::runtime_error("queue");
        work = std::move(job);
    }
};
struct Case {
    bool setup_fail{}, configure_fail{}, async{}, build_fail{}, queue_fail{};
};
void Setup(Notify* shader_notify, Queue& queue, Case test) {
MARK
#ifndef NEGATIVE_CONTROL
GUARD
#else
    [[maybe_unused]] bool build_handed_off = false;
#endif
    if (test.setup_fail) throw std::runtime_error("setup");
    if (test.configure_fail) throw std::runtime_error("configure");
    const auto build = [shader_notify, fail = test.build_fail] {
        // The real worker uses its own SCOPE_EXIT to publish completion even
        // when Validate/MakePipeline throws; preserve that one-shot contract.
        if (shader_notify) shader_notify->MarkShaderComplete();
        if (fail) return;
    };
    if (test.async) {
        queue.fail = test.queue_fail;
        queue.QueueWork(build);
        build_handed_off = true;
    } else {
        build_handed_off = true;
        build();
    }
}
void try_setup(Notify& notify, Queue& queue, Case test) {
    try { Setup(&notify, queue, test); }
    catch (const std::runtime_error&) {}
}
int main() {
#ifdef NEGATIVE_CONTROL
    Notify n; Queue q;
    try_setup(n, q, {.setup_fail=true});
    assert(n.building == 1 && n.outstanding == 1 && n.complete == 0);
    std::puts("OLD_SHADER_NOTIFY_LEAK_REPRODUCED");
#else
    for (Case test : {
        Case{.setup_fail=true}, Case{.configure_fail=true},
        Case{.async=true, .queue_fail=true},
        Case{}, Case{.build_fail=true},
        Case{.async=true}, Case{.async=true, .build_fail=true}
    }) {
        Notify n; Queue q;
        try_setup(n, q, test);
        const bool deferred = test.async && !test.setup_fail &&
                              !test.configure_fail && !test.queue_fail;
        if (deferred) {
            assert(n.outstanding == 1 && n.complete == 0);
            assert(static_cast<bool>(q.work));
            q.work();
        }
        assert(n.building == 1 && n.outstanding == 0 && n.complete == 1);
    }
    Queue no_notify;
    Setup(nullptr, no_notify, {.async=true});
    assert(static_cast<bool>(no_notify.work));
    no_notify.work();
    std::puts("PIPELINE_BUILD_HANDOFF_HOST_PASS");
#endif
}
"""
host = host.replace("MARK", mark).replace("GUARD", guard)

compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler missing"
with tempfile.TemporaryDirectory(prefix="eden-pipeline-handoff-") as temp:
    cpp = Path(temp) / "handoff.cpp"
    cpp.write_text(host)
    for opt in ("-O0", "-O2"):
        flags = [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all"]
        for negative in (False, True):
            exe = Path(temp) / ("handoff" + opt + ("old" if negative else "new"))
            cmd = [*flags, *(["-DNEGATIVE_CONTROL=1"] if negative else []),
                   str(cpp), "-o", str(exe)]
            built = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            assert built.returncode == 0, (opt, built.stderr[-3000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            expect = "OLD_SHADER_NOTIFY_LEAK_REPRODUCED" if negative else (
                "PIPELINE_BUILD_HANDOFF_HOST_PASS")
            assert run.returncode == 0 and expect in run.stdout, (
                opt, negative, run.stdout, run.stderr[-3000:])
            print("VULKAN_PIPELINE_BUILD_HANDOFF_PASS", opt,
                  "previous-leak" if negative else "maintained-scenarios")
