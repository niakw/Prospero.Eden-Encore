#!/usr/bin/env python3
"""GPU worker failure delivery/visibility contract under sanitized host C++.

The UI consumes each notification once. Waiters must still observe the same
fatal state until the old title's workers have all stopped and the next
launch boundary resets it. This is not a PS5 timing or FPS benchmark.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
header=(root/"headless/gpu_failure.h").read_text()
launcher=(root/"headless/main.cpp").read_text()
producer=(root/"tools/check-gpu-producer-failure-host.py").read_text()
sync=(root/"tools/check-gpu-sync-failure-host.py").read_text()
puller=(root/"tools/check-gpu-puller-acquire-failure-host.py").read_text()
assert "std::exception_ptr gpu_failure_latched" in header
assert "if (!gpu_failure_latched) gpu_failure_latched = error;" in header
assert "return gpu_failure_latched;" in header
assert "return std::exchange(gpu_failure, {});" in header
assert "void ResetGpuFailureForTitle()" in header
assert "ResetGpuFailureForTitle()" in producer and "ResetGpuFailureForTitle()" in puller
assert "ResetGpuFailureForTitle()" in sync
reset=launcher.index("Eden::ResetGpuFailureForTitle();")
assert launcher.count("Eden::ResetGpuFailureForTitle();") == 1
assert reset < launcher.index("Eden::Performance::ResetDirectMemoryProbeForTitle();")
assert reset < launcher.index("Eden::Performance::ResetGpuReportForTitle();")
assert reset < launcher.index("if (auto error = Eden::TakeGpuFailure())")

source=r"""
#include "gpu_failure.h"
#include <atomic>
#include <cassert>
#include <exception>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
int main() {
    Eden::ResetGpuFailureForTitle();
    assert(!Eden::PeekGpuFailure() && !Eden::TakeGpuFailure());
    Eden::RecordGpuFailure({});
    assert(!Eden::PeekGpuFailure() && !Eden::TakeGpuFailure());
    Eden::RecordGpuFailure(std::make_exception_ptr(std::runtime_error("first")));
    auto delivered = Eden::TakeGpuFailure();
    assert(delivered && !Eden::TakeGpuFailure());
    assert(Eden::PeekGpuFailure());
    std::atomic<unsigned> observed{0};
    std::vector<std::thread> waiters;
    for (unsigned i=0; i<8; ++i) {
        waiters.emplace_back([&] {
            try { std::rethrow_exception(Eden::PeekGpuFailure()); }
            catch (const std::runtime_error& error) {
                if (std::string(error.what()) == "first") ++observed;
            }
        });
    }
    for (auto& waiter : waiters) waiter.join();
    assert(observed.load() == 8);
    // Once consumed, a new fatal report may be delivered to the UI, while
    // in-flight waiters still read the FIRST cause of the fatal title.
    Eden::RecordGpuFailure(std::make_exception_ptr(std::runtime_error("second")));
    auto second=Eden::TakeGpuFailure();
    assert(second);
    try { std::rethrow_exception(second); }
    catch (const std::runtime_error& error) {
        assert(std::string(error.what())=="second");
    }
    try { std::rethrow_exception(Eden::PeekGpuFailure()); }
    catch (const std::runtime_error& error) {
        assert(std::string(error.what())=="first");
    }
    // Prior title is gone and all waiters joined; reset permits a new title.
    Eden::ResetGpuFailureForTitle();
    assert(!Eden::PeekGpuFailure() && !Eden::TakeGpuFailure());
    Eden::RecordGpuFailure(std::make_exception_ptr(std::runtime_error("next title")));
    try { std::rethrow_exception(Eden::PeekGpuFailure()); }
    catch (const std::runtime_error& error) {
        assert(std::string(error.what())=="next title");
    }
    Eden::ResetGpuFailureForTitle();
    assert(!Eden::PeekGpuFailure());
}
"""
compiler=os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-gpu-fatal-latch-") as tmp:
    source_file=Path(tmp)/"test.cpp"
    executable=Path(tmp)/"test"
    source_file.write_text(source)
    subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-pthread","-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    "-I",str(root/"headless"),str(source_file),"-o",str(executable)],
                   check=True,timeout=70,capture_output=True,text=True)
    result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,(result.stdout[-800:],result.stderr[-1500:])
print("GPU_FATAL_LATCH_HOST_PASS ui_once=1 waiters=8 sticky_first=1 title_reset=1 asan_ubsan=1")
