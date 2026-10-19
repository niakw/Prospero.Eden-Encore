#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R301: execute the actual PS5-generated A32/A64 Dynarmic Run wrapper.

In quiet mode the wrapper must not evaluate GetPC/GetFpcr/Regs/Fpscr or
GetSvcNumber just to call a profiler which would immediately return.
The guest Run, CPU phase transitions and result translation must remain.
This is a C++20 host mock, NOT PS5 firmware or gameplay qualification.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
assert 'list(APPEND core_sources "${EDEN_G11_SOURCE}")' in cmake
assert 'string(REPLACE "    return TranslateHaltReason(m_jit->Run());"' not in cmake
assert "EDEN_G11_PROFILE" in cmake

def generated(bits: int) -> str:
    owned = root/"vendor/encore-active/eden-core/src/core/arm/dynarmic/g11"
    host_unit = (owned/f"arm_dynarmic_{bits}_host_dev.cpp").read_text()
    native_unit = (owned/f"arm_dynarmic_{bits}_native_dev.cpp").read_text()
    signature = f"HaltReason ArmDynarmic{bits}::RunThread(Kernel::KThread* thread) {{"
    def body(unit: str) -> str:
        assert unit.count(signature) == 1
        start = unit.index(signature) + len(signature)
        finish = unit.index("\n}", start)
        inner = unit[start:finish]
        assert inner.count("m_jit->ClearExclusiveState();") == 1
        return inner.split("m_jit->ClearExclusiveState();", 1)[1].lstrip("\n") + "\n"
    selected = body(host_unit)
    assert selected == body(native_unit), ("DEV JIT CPU sampling platform drift", bits)
    for token in ("const bool eden_detailed_cpu_sample =",
                  "cpu_state[m_core_index].phase.store(",
                  "return TranslateHaltReason(halt);"):
        assert token in selected
    assert selected.count("::Eden::Performance::SampleCpu(") == 2
    assert selected.count("m_jit->Run()") == 1
    assert selected.count("if (eden_detailed_cpu_sample &&") == 2
    return selected

host = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
namespace Eden::Performance {
enum class CpuPhase : unsigned { Kernel, Guest, Idle };
struct State { std::atomic<CpuPhase> phase{CpuPhase::Kernel}; };
std::array<State, 4> cpu_state{};
std::atomic<bool> detailed_gpu_profile{false};
std::atomic<unsigned> samples{0}, due_checks{0};
std::atomic<bool> sample_allowed{true};
std::atomic<unsigned long long> last_thread{0};
bool CpuSampleDue(std::size_t) { ++due_checks; return sample_allowed.load(); }
void SampleCpu(std::size_t, unsigned long long thread, unsigned long long,
               unsigned, unsigned) { ++samples; last_thread.store(thread); }
}
namespace Kernel {
std::atomic<unsigned> lookups{0};
struct GuestThread { unsigned long long GetThreadId() const { return 789; } };
GuestThread GetCurrentThread(int) { ++lookups; return {}; }
}
struct Jit {
    int run_calls=0, guest_phase_observed=0;
    int get_pc=0, get_fpcr=0, regs_calls=0, fpscr_calls=0;
    std::array<unsigned long long,16> registers{};
    int Run() {
        ++run_calls;
        if (Eden::Performance::cpu_state[0].phase.load() ==
            Eden::Performance::CpuPhase::Guest) ++guest_phase_observed;
        return 77;
    }
    unsigned long long GetPC() { ++get_pc; return 0x123456; }
    unsigned GetFpcr() { ++get_fpcr; return 0; }
    std::array<unsigned long long,16>& Regs() { ++regs_calls; return registers; }
    unsigned Fpscr() { ++fpscr_calls; return 0; }
};
struct Fixture {
    Jit jit{};
    Jit* m_jit=&jit;
    struct System { int Kernel() const { return 1; } } m_system;
    std::size_t m_core_index=0;
    unsigned svc_calls=0;
    unsigned GetSvcNumber() { ++svc_calls; return 11; }
    int TranslateHaltReason(int value) { return value; }
    int Run64() {
A64_CODE
    }
    int Run32() {
A32_CODE
    }
};
int main() {
    Fixture fixture;
    for (int i=0; i<20000; ++i) {
        assert(fixture.Run64()==77);
        assert(fixture.Run32()==77);
    }
    assert(fixture.jit.run_calls == 40000);
    assert(fixture.jit.guest_phase_observed == 40000);
    assert(fixture.jit.get_pc == 0 && fixture.jit.get_fpcr == 0);
    assert(fixture.jit.regs_calls == 0 && fixture.jit.fpscr_calls == 0);
    assert(fixture.svc_calls == 0 && Eden::Performance::samples == 0);
    assert(Eden::Performance::due_checks == 0 && Kernel::lookups == 0);
    assert(Eden::Performance::cpu_state[0].phase.load() ==
           Eden::Performance::CpuPhase::Kernel);
    Eden::Performance::detailed_gpu_profile.store(true);
    assert(fixture.Run64()==77 && fixture.Run32()==77);
    assert(fixture.jit.get_pc == 2 && fixture.jit.get_fpcr == 2);
    assert(fixture.jit.regs_calls == 2 && fixture.jit.fpscr_calls == 2);
    assert(fixture.svc_calls == 4 && Eden::Performance::samples == 4);
    assert(Eden::Performance::due_checks == 4 && Kernel::lookups == 4);
    assert(Eden::Performance::last_thread == 789);
    Eden::Performance::sample_allowed.store(false);
    assert(fixture.Run64()==77 && fixture.Run32()==77);
    assert(Eden::Performance::due_checks == 8 && Kernel::lookups == 4);
    assert(fixture.svc_calls == 4 && Eden::Performance::samples == 4);
    Eden::Performance::detailed_gpu_profile.store(false);
    assert(fixture.Run64()==77 && fixture.Run32()==77);
    assert(fixture.jit.get_pc == 2 && fixture.jit.get_fpcr == 2);
    assert(fixture.jit.regs_calls == 2 && fixture.jit.fpscr_calls == 2);
    assert(fixture.svc_calls == 4 && Eden::Performance::samples == 4);
    assert(fixture.jit.run_calls == 40006);
    assert(fixture.jit.guest_phase_observed == 40006);
    assert(Kernel::lookups == 4);
    std::puts("PASS: real A32/A64 Run wrappers skip quiet register sampling and preserve phases/results");
}
""".replace("A64_CODE", generated(64)).replace("A32_CODE", generated(32))

compiler = next((name for name in ("clang++-18","clang++","g++") if shutil.which(name)), None)
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-guest-entry-") as directory:
    source = Path(directory) / "guest_entry.cpp"
    binary = Path(directory) / "guest_entry"
    source.write_text(host)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-pthread", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=15)
print("HOST ONLY: no PS5 native SDK, FW13.60 runtime or FPS measured.")
