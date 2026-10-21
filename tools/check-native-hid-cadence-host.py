#!/usr/bin/env python3
"""C++20 host witness for the shipping HID polling period and unchanged scheduler."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-core/src/hid_core/resource_manager.cpp").read_text()
original = (root / "vendor/sources/eden/src/hid_core/resource_manager.cpp").read_text()
definition = "constexpr auto npad_update_ns = std::chrono::nanoseconds{4 * 1000 * 1000};"
assert src.count(definition) == 1
assert "ScheduleLoopingEvent(npad_update_ns, npad_update_ns, npad_update_event);" in src
assert "std::chrono::nanoseconds{1 * 1000 * 1000}" in original
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
program = """#include <cassert>
#include <chrono>
""" + definition + """
int main(){
    using namespace std::chrono;
    static_assert(npad_update_ns == 4ms);
    static_assert(1s / npad_update_ns == 250);
    static_assert((1s / 1ms) / (1s / npad_update_ns) == 4);
    assert(npad_update_ns.count() == 4000000);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-hid-interval-") as d:
    path=Path(d)/"test.cpp"
    exe=Path(d)/"test"
    path.write_text(program)
    subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
        str(path),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=90)
print("HID_NATIVE_CADENCE_PASS poll_rate=250Hz reduction=4x host_only=1")
