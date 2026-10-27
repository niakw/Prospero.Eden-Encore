#!/usr/bin/env python3
"""Source-extracted compute ShaderNotify transfer, failure-before/pass-after host."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
ctor = src[src.index("ComputePipeline::ComputePipeline("):src.index("void ComputePipeline::PreflightDescriptorScratch()")]
mark = """    if (shader_notify) {
        shader_notify->MarkShaderBuilding();
    }
"""
assert ctor.count(mark) == 1
a = ctor.index("#ifdef PS5_NATIVE\n    // Layout setup and worker queue admission")
b = ctor.index("#endif\n", a) + len("#endif\n")
guard = ctor[a:b]
start = "    if (thread_worker) {\n        thread_worker->QueueWork(std::move(func));"
i = ctor.index(start)
j = ctor.index("\n}", i)
handoff = ctor[i:j]
assert "if (!build_handed_off && shader_notify)" in guard
assert handoff.count("build_handed_off = true;") == 2
assert handoff.index("thread_worker->QueueWork(std::move(func));") < handoff.index("build_handed_off = true;")
assert "F07 compute shader build notification unwind" in gen
assert "F07 compute worker completion ownership transfer" in gen

test = r"""
#include <cassert>
#include <cstdio>
#include <functional>
#include <stdexcept>
#include <type_traits>
#include <utility>
struct Maker {};
template<class F> struct ScopeGuard { F f; ~ScopeGuard() { f(); } };
template<class F> ScopeGuard<std::decay_t<F>> operator+(Maker, F&& f) {
    return {std::forward<F>(f)};
}
#define SCOPE_EXIT auto _scope = Maker{} + [&]
struct Notify {
    int start{}, done{}, pending{};
    void MarkShaderBuilding() { ++start; ++pending; }
    void MarkShaderComplete() { ++done; assert(pending > 0); --pending; }
};
struct Worker {
    std::function<void()> job;
    bool reject{};
    void QueueWork(std::function<void()> fn) {
        if (reject) throw std::runtime_error("queue");
        job = std::move(fn);
    }
};
void Build(Notify* shader_notify, Worker* thread_worker, bool fail_setup) {
MARK
#ifndef OLD_BUG
GUARD
#else
    [[maybe_unused]] bool build_handed_off = false;
#endif
    if (fail_setup) throw std::runtime_error("layout");
    auto func = [shader_notify] {
        if (shader_notify) shader_notify->MarkShaderComplete();
    };
HANDOFF
}
void Try(Notify* n, Worker* w, bool setup) {
    try { Build(n, w, setup); } catch (const std::runtime_error&) {}
}
int main() {
#ifdef OLD_BUG
    Notify old;
    Try(&old, nullptr, true);
    assert(old.start == 1 && old.done == 0 && old.pending == 1);
    std::puts("COMPUTE_NOTIFY_LEAK_BEFORE");
#else
    Notify a;
    Try(&a, nullptr, false);
    assert(a.start == 1 && a.done == 1 && a.pending == 0);
    Notify b;
    Try(&b, nullptr, true);
    assert(b.start == 1 && b.done == 1 && b.pending == 0);
    Worker bad;
    bad.reject = true;
    Notify c;
    Try(&c, &bad, false);
    assert(c.start == 1 && c.done == 1 && c.pending == 0 && !bad.job);
    Worker good;
    Notify d;
    Try(&d, &good, false);
    assert(d.start == 1 && d.done == 0 && d.pending == 1 && good.job);
    good.job();
    assert(d.done == 1 && d.pending == 0);
    Worker empty;
    Try(nullptr, &empty, false);
    assert(empty.job);
    empty.job();
    std::puts("COMPUTE_NOTIFY_HANDOFF_PASS");
#endif
}
"""
test = test.replace("MARK", mark).replace("GUARD", guard).replace("HANDOFF", handoff)
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-compute-notify-") as directory:
    path = Path(directory) / "notify.cpp"
    path.write_text(test)
    for opt in ("-O0", "-O2"):
        for old in (True, False):
            exe = Path(directory) / (opt[1:] + ("-old" if old else "-fixed"))
            subprocess.run([compiler, "-std=c++20", opt, "-DPS5_NATIVE",
                            "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                            "-fno-sanitize-recover=all",
                            *([] if not old else ["-DOLD_BUG"]), str(path), "-o", str(exe)],
                           check=True, timeout=40)
            result = subprocess.run([str(exe)], capture_output=True, text=True,
                                    check=True, timeout=15)
            assert ("COMPUTE_NOTIFY_LEAK_BEFORE" if old else
                    "COMPUTE_NOTIFY_HANDOFF_PASS") in result.stdout
print("F07_COMPUTE_NOTIFY_HANDOFF_PASS before=leak after=balanced O0=1 O2=1")
