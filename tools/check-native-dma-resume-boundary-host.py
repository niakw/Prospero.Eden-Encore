#!/usr/bin/env python3
"""Execute pinned DMA dispatcher, step and decoder to reject naive resume.

Host-only fixture supplies fake memory and method side effects. Tests expose
duplicate execution when DispatchCalls is restarted after a completed Step,
or when an exception interrupts ProcessCommands after a method side effect.
It deliberately proposes NO native fix and does not enable bridge #187.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
read = lambda p: (root / p).read_text()
pinned = read("vendor/sources/eden/src/video_core/dma_pusher.cpp")
header = read("vendor/sources/eden/src/video_core/dma_pusher.h")
worker = read("vendor/sources/eden/src/video_core/gpu_thread.cpp")
scheduler = read("vendor/sources/eden/src/video_core/control/scheduler.cpp")
replay = read("headless/gpu_deferred_replay.h")
workflow = read(".github/workflows/encore-core-preflight.yml")

def extract(begin, end):
    assert pinned.count(begin) == 1, begin
    assert pinned.count(end) == 1, end
    return begin + pinned.split(begin, 1)[1].split(end, 1)[0]

dispatcher = extract("void DmaPusher::DispatchCalls() {", "\nbool DmaPusher::Step() {")
step = extract("bool DmaPusher::Step() {", "\nvoid DmaPusher::ProcessCommands")
process = extract("void DmaPusher::ProcessCommands(std::span<const CommandHeader> commands) {",
                  "\nvoid DmaPusher::SetState(")
set_state = extract("void DmaPusher::SetState(const CommandHeader& command_header) {",
                    "\nvoid DmaPusher::CallMethod(")
assert "dma_pushbuffer_subindex = 0;" in dispatcher
assert "while (system.IsPoweredOn())" in dispatcher
assert "system.GPU().OnCommandListEnd();" in dispatcher
assert "if (++dma_pushbuffer_subindex >= command_list_size)" in step
assert "dma_pushbuffer.pop();" in step
assert "for (size_t index = 0; index < commands.size();" in process
assert "CallMethod(command_header.arg_count);" in process
assert "CallMultiMethod(&command_header.argument, max_write);" in process
assert "boost::container::small_vector<CommandListHeader, 512> command_lists;" in header
assert "scheduler.Push(system.GPU(), submit_list->channel, std::move(submit_list->entries));" in worker
assert "channel_state->payload->dma_pusher.DispatchCalls();" in scheduler
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert "python3 -B tools/check-native-dma-resume-boundary-host.py" in workflow

prelude = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <map>
#include <mutex>
#include <queue>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s64 = std::int64_t;
static bool test_safe = false;
namespace Settings {
bool IsDMALevelDefault() { return true; }
bool IsGPULevelHigh() { return test_safe; }
bool IsDMALevelSafe() { return false; }
struct Option { bool GetValue() const { return false; } };
struct Values { Option sync_memory_operations; };
inline Values values;
}
struct FakeGPU {
    unsigned flushes = 0, command_list_ends = 0;
    void FlushCommands() { ++flushes; }
    void OnCommandListEnd() { ++command_list_ends; }
};
struct FakeSystem {
    int budget = 20;
    FakeGPU gpu;
    bool IsPoweredOn() { if (budget <= 0) return false; --budget; return true; }
    FakeGPU& GPU() { return gpu; }
};
namespace Tegra {
constexpr u32 MacroRegistersStart = 0xe00;
enum class SubmissionMode : u32 {
    Increasing = 1, NonIncreasing = 3, Inline = 4, IncreaseOnce = 5
};
struct CommandHeader {
    u32 argument = 0, method = 0, subchannel = 0;
    u32 arg_count = 0, method_count = 0;
    SubmissionMode mode = SubmissionMode::Inline;
};
struct CommandListHeader { u64 addr = 0; u32 size = 0; bool sync = false; };
struct CommandList {
    std::vector<CommandListHeader> command_lists;
    std::vector<CommandHeader> prefetch_command_list;
};
struct MemoryManager {
    std::map<u64, std::vector<CommandHeader>> ram;
    bool IsMemoryDirty(u64, std::size_t) { return false; }
    std::vector<CommandHeader> Read(u64 addr, std::size_t count) {
        auto v = ram.at(addr);
        assert(v.size() >= count);
        v.resize(count);
        return v;
    }
};
namespace Memory {
enum class GuestMemoryFlags { SafeRead, UnsafeRead };
template <typename T, GuestMemoryFlags flags>
struct GpuGuestMemory {
    std::vector<T> snapshot;
    GpuGuestMemory(MemoryManager& mem, u64 addr, std::size_t n, std::vector<T>*)
        : snapshot(mem.Read(addr, n)) {}
    operator std::span<const T>() const { return {snapshot.data(), snapshot.size()}; }
};
}
struct FakeChannel { bool current_dirty = false; };
struct FakeRasterizer { void SignalFence(std::function<void()> f) { f(); } };
struct PauseAfterMethod : std::exception {};
struct DmaPusher {
    DmaPusher(FakeSystem& sys, MemoryManager& mem) : system(sys), memory_manager(mem) {}
    FakeSystem& system;
    MemoryManager& memory_manager;
    std::queue<CommandList> dma_pushbuffer;
    std::size_t dma_pushbuffer_subindex = 0;
    struct State {
        u32 method = 0, subchannel = 0, method_count = 0;
        u64 dma_get = 0, dma_word_offset = 0;
        bool non_incrementing = false, is_last_call = false;
    } dma_state;
    std::array<FakeChannel*, 8> subchannels{};
    bool ib_enable = true, signal_sync = false, synced = false, dma_increment_once = false;
    std::mutex sync_mutex;
    std::condition_variable sync_cv;
    FakeRasterizer owned_rasterizer;
    FakeRasterizer* rasterizer = &owned_rasterizer;
    std::vector<CommandHeader> command_headers;
    std::vector<u32> observed;
    bool pause_after_first_effect = false;
    void Push(CommandList&& list) { dma_pushbuffer.push(std::move(list)); }
    void DispatchCalls();
    bool Step();
    void ProcessCommands(std::span<const CommandHeader> commands);
    void SetState(const CommandHeader& h);
    void CallMethod(u32 arg) {
        observed.push_back(arg);
        if (pause_after_first_effect) {
            pause_after_first_effect = false;
            throw PauseAfterMethod{};
        }
    }
    void CallMultiMethod(const u32* args, u32 count) {
        for (u32 n = 0; n < count; ++n) CallMethod(args[n]);
    }
};
}
"""
tests = r"""
static Tegra::CommandHeader Inline(u32 value) {
    Tegra::CommandHeader c;
    c.mode = Tegra::SubmissionMode::Inline;
    c.method = 0x50;
    c.arg_count = value;
    return c;
}
static Tegra::CommandList TwoSegments() {
    Tegra::CommandList c;
    c.command_lists.push_back({0x1000, 1, false});
    c.command_lists.push_back({0x2000, 1, false});
    return c;
}
static void InitMem(Tegra::MemoryManager& memory) {
    memory.ram[0x1000] = {Inline(11)};
    memory.ram[0x2000] = {Inline(22)};
}
static void CompleteNormally(bool safe) {
    test_safe = safe;
    FakeSystem sys;
    Tegra::MemoryManager mem;
    InitMem(mem);
    Tegra::DmaPusher dma(sys, mem);
    dma.Push(TwoSegments());
    dma.DispatchCalls();
    assert((dma.observed == std::vector<u32>{11, 22}));
    assert(dma.dma_pushbuffer.empty());
    assert(sys.gpu.flushes == 1 && sys.gpu.command_list_ends == 1);
}
static void RestartDispatcherDuplicatesStep(bool safe) {
    test_safe = safe;
    FakeSystem sys;
    sys.budget = 1; // Cut the dispatcher BETWEEN two completed Step calls.
    Tegra::MemoryManager mem;
    InitMem(mem);
    Tegra::DmaPusher dma(sys, mem);
    dma.Push(TwoSegments());
    dma.DispatchCalls();
    assert((dma.observed == std::vector<u32>{11}));
    assert(dma.dma_pushbuffer_subindex == 1);
    assert(!dma.dma_pushbuffer.empty());
    sys.budget = 10;
    dma.DispatchCalls(); // Native dispatcher unconditionally resets subindex.
    assert((dma.observed == std::vector<u32>{11, 11, 22}));
    assert(dma.dma_pushbuffer.empty());
    assert(sys.gpu.flushes == 2 && sys.gpu.command_list_ends == 2);
}
static void ThrowInsideMethodDuplicatesEffect(bool safe) {
    test_safe = safe;
    FakeSystem sys;
    Tegra::MemoryManager mem;
    InitMem(mem);
    Tegra::DmaPusher dma(sys, mem);
    dma.Push(TwoSegments());
    dma.pause_after_first_effect = true;
    bool caught = false;
    try { (void)dma.Step(); }
    catch (const Tegra::PauseAfterMethod&) { caught = true; }
    assert(caught && dma.dma_pushbuffer_subindex == 0);
    assert((dma.observed == std::vector<u32>{11}));
    assert(dma.Step() && dma.Step());
    assert((dma.observed == std::vector<u32>{11, 11, 22}));
}
static void StepCursorAloneDoesNotDuplicate(bool safe) {
    test_safe = safe;
    FakeSystem sys;
    Tegra::MemoryManager mem;
    InitMem(mem);
    Tegra::DmaPusher dma(sys, mem);
    dma.Push(TwoSegments());
    assert(dma.Step());
    assert(dma.dma_pushbuffer_subindex == 1);
    assert(dma.Step());
    assert((dma.observed == std::vector<u32>{11, 22}));
    assert(dma.dma_pushbuffer.empty());
    // Not a proposed production resume: Step by itself omits final
    // FlushCommands and OnCommandListEnd from DispatchCalls.
    assert(sys.gpu.flushes == 0 && sys.gpu.command_list_ends == 0);
}
int main() {
    for (bool safe : {false, true}) {
        CompleteNormally(safe);
        RestartDispatcherDuplicatesStep(safe);
        ThrowInsideMethodDuplicatesEffect(safe);
        StepCursorAloneDoesNotDuplicate(safe);
    }
    std::puts("PINNED_DMA_DISPATCH_RESTART_DUPLICATE_NEGATIVE_PASS");
    std::puts("PINNED_DMA_METHOD_PARTIAL_EFFECT_DUPLICATE_NEGATIVE_PASS");
    std::puts("PINNED_DMA_STEP_CURSOR_ONLY_INCOMPLETE_FINALIZATION_PASS");
    std::puts("DMA_RESUME_NATIVE_BRIDGE_NOT_QUALIFIED");
}
"""
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-dma-resume-") as folder:
    source = Path(folder) / "pinned_dma_resume.cpp"
    executable = Path(folder) / "pinned_dma_resume"
    source.write_text(prelude + "\nnamespace Tegra {\n" + dispatcher + "\n" + step + "\n"
                      + process + "\n" + set_state + "\n} // namespace Tegra\n" + tests)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-pthread", str(source), "-o", str(executable)],
                   check=True)
    result = subprocess.run([str(executable)], text=True, capture_output=True,
                            timeout=15, check=True)
    print(result.stdout, end="")
