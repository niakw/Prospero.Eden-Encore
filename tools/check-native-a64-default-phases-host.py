#!/usr/bin/env python3
"""Exercise actual default A64 non-batch compilation using source-extracted code.

Release and quiet DEV must not sample phases. Detailed DEV must call the
existing phase hook once per compiled block, with its real guest location.
This is a host semantic fixture, not a native-console FPS experiment.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
A64 = ROOT / "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp"
text = A64.read_text()
batch_anchor = "#if defined(EDEN_JIT_A64_BATCH)\n"
assert text.count(batch_anchor) == 1
nonbatch = "#else\n        const auto get_code = [this](u64 vaddr)"
assert text.count(nonbatch) == 1
start = text.index(nonbatch) + len("#else\n")
end = text.index("\n#endif\n    }\n\n    void PerformRequestedCacheInvalidation", start)
method = text[start:end]
timer_start = text.index("        struct EdenCompileTimer {")
timer_end = "        } eden_compile_timer{unsigned(conf.processor_id)};"
timer = text[timer_start:text.index(timer_end, timer_start) + len(timer_end)]
assert "eden_phase_timing = eden_compile_timer.active && eden_jit_phases" in method
assert "#if defined(EDEN_JIT_A64_DEV_PROFILE)" in method
assert "descriptor.Value()" in method
assert "return entrypoint;" in method
assert "#if defined(EDEN_JIT_A64_BATCH)" not in method

program = r"""
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <optional>
using u64 = std::uint64_t;
static bool detailed = false;
static unsigned compile_calls = 0, phase_calls = 0;
static unsigned last_core = 99;
static unsigned long long last_location = 0;
static unsigned long long phase_total = 0;
extern "C" bool eden_native_detailed_logging() noexcept __attribute__((weak));
extern "C" void eden_jit_compile(unsigned, unsigned long long) __attribute__((weak));
extern "C" void eden_jit_phases(unsigned, unsigned long long, unsigned long long,
                                 unsigned long long, unsigned long long) __attribute__((weak));
extern "C" bool eden_native_detailed_logging() noexcept { return detailed; }
extern "C" void eden_jit_compile(unsigned core, unsigned long long ns) {
    assert(core == 2 && ns > 0);
    ++compile_calls;
}
extern "C" void eden_jit_phases(unsigned core, unsigned long long translated,
                                 unsigned long long optimized, unsigned long long emitted,
                                 unsigned long long location) {
    last_core = core;
    last_location = location;
    phase_total += translated + optimized + emitted;
    ++phase_calls;
}
namespace IR {
struct LocationDescriptor {
    unsigned long long value;
    unsigned long long Value() const { return value; }
};
}
namespace A64 {
struct LocationDescriptor {
    IR::LocationDescriptor value;
    explicit LocationDescriptor(IR::LocationDescriptor v) : value(v) {}
};
struct TranslationOpts { bool unpredictable; bool wall_clock; };
template<class F, class B>
void Translate(B& block, const LocationDescriptor&, F&& get_code, TranslationOpts) {
    assert(get_code(0x1000) == std::optional<std::uint32_t>{42});
    ++block.translate;
}
}
struct Block {
    unsigned translate = 0, optimize = 0, emit = 0;
    void Reset(const A64::LocationDescriptor&) {}
};
struct Emitter {
    struct Emitted { unsigned long long entrypoint; };
    Emitted Emit(Block& block) { ++block.emit; return {0x12345678}; }
};
struct Callback {
    std::optional<std::uint32_t> MemoryReadCode(u64) const { return 42; }
};
struct Config {
    Callback* callbacks = nullptr;
    bool define_unpredictable_behaviour = true;
    bool wall_clock_cntpct = false;
    unsigned processor_id = 2;
};
namespace Optimization {
void Optimize(Block& block, const Config&, int) { ++block.optimize; }
}
struct Probe {
    Callback callback;
    Config conf{&callback};
    Block ir_block{};
    Emitter emitter{};
    int polyfill_options = 0;
    unsigned long long Run(IR::LocationDescriptor descriptor) {
#if defined(EDEN_JIT_A64_DEV_PROFILE)
INJECT_TIMER
#endif
INJECT_NONBATCH
    }
};
int main() {
    Probe p;
    for (unsigned i = 0; i < 1000; ++i)
        assert(p.Run(IR::LocationDescriptor{0x1234}) == 0x12345678);
    assert(p.ir_block.translate == 1000 && p.ir_block.optimize == 1000 && p.ir_block.emit == 1000);
    assert(!phase_calls && !compile_calls);
    detailed = true;
    assert(p.Run(IR::LocationDescriptor{0x5555}) == 0x12345678);
#if defined(EDEN_JIT_A64_DEV_PROFILE)
    assert(phase_calls == 1 && compile_calls == 1 && phase_total > 0);
    assert(last_core == 2 && last_location == 0x5555);
#else
    assert(!phase_calls && !compile_calls);
#endif
    detailed = false;
    for (unsigned i = 0; i < 1000; ++i)
        assert(p.Run(IR::LocationDescriptor{0x5555}) == 0x12345678);
#if defined(EDEN_JIT_A64_DEV_PROFILE)
    assert(phase_calls == 1 && compile_calls == 1);
#else
    assert(!phase_calls && !compile_calls);
#endif
    std::puts("A64_DEFAULT_PHASES_HOST_PASS");
}
""".replace("INJECT_TIMER", timer).replace("INJECT_NONBATCH", method)
compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "A C++20 compiler is required"
with tempfile.TemporaryDirectory(prefix="encore-a64-phases-") as tmp:
    p = Path(tmp)
    source = p / "main.cpp"
    source.write_text(program)
    for name, flags in (("release", []), ("dev", ["-DEDEN_JIT_A64_DEV_PROFILE=1"])):
        exe = p / name
        subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        *flags, str(source), "-o", str(exe)],
                       check=True, timeout=70, capture_output=True, text=True)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, (name, result.stdout, result.stderr)
print("ENCORE_A64_DEFAULT_PHASES_PASS source_extracted=1 release_quiet=1 dev_quiet=1 dev_detailed=1 asan_ubsan=1")
