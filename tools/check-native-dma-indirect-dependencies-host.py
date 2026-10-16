#!/usr/bin/env python3
"""Compile the unchanged pinned DmaPusher::Step() with host-only stubs.

Identical SubmitList metadata does not seal indirect command payloads.
This executes the real Step body, NOT actual command semantics, device
memory management, Vulkan fences or runtime GPU coherency.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
def read(path):
    return (root / path).read_text()

source = read("vendor/sources/eden/src/video_core/dma_pusher.cpp")
head = read("vendor/sources/eden/src/video_core/dma_pusher.h")
scheduler = read("vendor/sources/eden/src/video_core/control/scheduler.cpp")
worker = read("vendor/sources/eden/src/video_core/gpu_thread.cpp")
replay = read("headless/gpu_deferred_replay.h")
workflow = read(".github/workflows/encore-core-preflight.yml")
start = "bool DmaPusher::Step() {"
end = "\nvoid DmaPusher::ProcessCommands"
assert source.count(start) == 1 and source.count(end) == 1
actual_step = start + source.split(start, 1)[1].split(end, 1)[0]
for marker in (
    "command_list.command_lists[dma_pushbuffer_subindex]",
    "dma_state.dma_get = header.addr;",
    "GpuGuestMemory<Tegra::CommandHeader, Tegra::Memory::GuestMemoryFlags::SafeRead>",
    "GpuGuestMemory<Tegra::CommandHeader, Tegra::Memory::GuestMemoryFlags::UnsafeRead>",
    "ProcessCommands(headers);",
):
    assert marker in actual_step, marker
assert "boost::container::small_vector<CommandListHeader, 512> command_lists;" in head
assert "boost::container::small_vector<CommandHeader, 512> prefetch_command_list;" in head
assert "channel_state->payload->dma_pusher.DispatchCalls();" in scheduler
assert "scheduler.Push(system.GPU(), submit_list->channel, std::move(submit_list->entries));" in worker
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert "python3 -B tools/check-native-dma-indirect-dependencies-host.py" in workflow

prelude = r"""
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
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
static bool test_safe_reads = false;
namespace Settings {
inline bool IsDMALevelDefault() { return true; }
inline bool IsGPULevelHigh() { return test_safe_reads; }
inline bool IsDMALevelSafe() { return false; }
struct Option { bool GetValue() const { return false; } };
struct Values { Option sync_memory_operations; };
inline Values values;
}
namespace Tegra {
struct CommandHeader { u32 argument = 0; };
struct CommandListHeader { u64 addr = 0; u32 size = 0; bool sync = false; };
struct CommandList {
    std::vector<CommandListHeader> command_lists;
    std::vector<CommandHeader> prefetch_command_list;
};
struct MemoryManager {
    std::map<u64, std::vector<CommandHeader>> ram;
    bool IsMemoryDirty(u64, std::size_t) { return true; }
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
    GpuGuestMemory(MemoryManager& m, u64 addr, std::size_t n, std::vector<T>*)
        : snapshot(m.Read(addr, n)) {}
    auto begin() const { return snapshot.begin(); }
    auto end() const { return snapshot.end(); }
};
}
struct FakeRasterizer { void SignalFence(std::function<void()> f) { f(); } };
struct FakeChannel { bool current_dirty = false; };
struct DmaPusher {
    bool ib_enable = true;
    std::queue<CommandList> dma_pushbuffer;
    std::size_t dma_pushbuffer_subindex{};
    struct { bool is_last_call = false; u64 dma_get = 0; u32 method = 0, subchannel = 0; } dma_state;
    bool signal_sync = false, synced = false;
    std::mutex sync_mutex;
    std::condition_variable sync_cv;
    static constexpr u32 MacroRegistersStart = 0xe00;
    std::array<FakeChannel*, 8> subchannels{};
    MemoryManager memory_manager;
    FakeRasterizer owned_rasterizer;
    FakeRasterizer* rasterizer = &owned_rasterizer;
    std::vector<CommandHeader> command_headers;
    std::vector<u32> decoded;
    template <class C> void ProcessCommands(const C& headers) {
        for (auto const& h : headers) decoded.push_back(h.argument);
    }
    bool Step();
};
}
using Tegra::DmaPusher;
"""
postlude = r"""
int main() {
    // Same submitted list address, size and sync flag in all cases.
    // Only the RAM-backed command payload differs when Step executes.
    for (bool safe : {false, true}) {
        test_safe_reads = safe;
        for (u32 encoded : {u32{0x2000}, u32{0x3000}}) {
            DmaPusher pusher;
            pusher.memory_manager.ram[0x1000] = {{encoded}};
            Tegra::CommandList list;
            list.command_lists.push_back({0x1000, 1, false});
            pusher.dma_pushbuffer.push(std::move(list));
            assert(pusher.Step());
            assert(pusher.decoded.size() == 1 && pusher.decoded[0] == encoded);
        }
    }
    // Mutation between enqueue and execution is visible at Step's late read.
    DmaPusher delayed;
    delayed.memory_manager.ram[0x1000] = {{0x2000}};
    Tegra::CommandList list;
    list.command_lists.push_back({0x1000, 1, false});
    delayed.dma_pushbuffer.push(std::move(list));
    delayed.memory_manager.ram[0x1000] = {{0x5000}};
    assert(delayed.Step());
    assert(delayed.decoded.size() == 1 && delayed.decoded[0] == 0x5000);
    std::puts("PINNED_DMA_STEP_LATE_INDIRECT_DECODE_PASS");
}
"""
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler, "C++20 compiler required for host test"
with tempfile.TemporaryDirectory(prefix="encore-gpu-command-read-") as folder:
    path = Path(folder) / "pinned_step.cpp"
    binary = Path(folder) / "pinned_step"
    path.write_text(prelude + actual_step + "\n" + postlude)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-pthread", str(path), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True,
                            timeout=15, check=True)
    print(result.stdout, end="")
