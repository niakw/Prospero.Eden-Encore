#!/usr/bin/env python3
"""F07 PS5 hot transition memo: compile exact selected Next() in four host modes.

A long overlay/scene transition list previously reread every prior full key on
each repeated transition. Verify one-entry memo is a stable INDEX (not a vector
pointer), preserves misses, short lists, self transitions and appends, and does
not affect non-PS5 builds. This is a CPU lookup optimization, not an FPS proof.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
begin = "    [[nodiscard]] GraphicsPipeline* Next(const GraphicsPipelineCacheKey& current_key) noexcept {"
end = "\n\n    [[nodiscard]] bool IsBuilt() const noexcept {"
assert header.count(begin) == 1
assert header.count(end) == 1
selected = begin + header.split(begin, 1)[1].split(end, 1)[0]
assert selected.count("hot_transition_index") == 3
assert header.count("    size_t hot_transition_index{};") == 1
assert "transition_source.count(transition_next_old) != 1" in generator
assert "transition_source.replace(transition_next_old, transition_next_new, 1)" in generator
assert "transition_member_old" in generator and "transition_member_new" in generator
assert "std::vector<GraphicsPipeline*> transitions;" in header

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <vector>
struct GraphicsPipelineCacheKey {
    int value{};
    static inline std::size_t comparisons = 0;
    bool operator==(const GraphicsPipelineCacheKey& other) const noexcept {
        ++comparisons;
        return value == other.value;
    }
};
struct GraphicsPipeline {
    GraphicsPipelineCacheKey key{};
    std::vector<GraphicsPipelineCacheKey> transition_keys;
    std::vector<GraphicsPipeline*> transitions;
#ifdef PS5_NATIVE
    size_t hot_transition_index{};
#endif
""" + selected + r"""
    void AddTransition(GraphicsPipeline* other) {
        transition_keys.push_back(other->key);
        transitions.push_back(other);
    }
};
int main() {
    GraphicsPipeline source{};
    source.key.value = -1;
    std::array<GraphicsPipeline, 64> targets{};
    for (int i = 0; i < 48; ++i) {
        targets[i].key.value = i;
        source.AddTransition(&targets[i]);
    }
    assert(source.Next(source.key) == &source);
    assert(source.Next(GraphicsPipelineCacheKey{999}) == nullptr);
    assert(source.Next(targets[35].key) == &targets[35]);
    for (int r = 0; r < 2000; ++r) {
        GraphicsPipelineCacheKey::comparisons = 0;
        assert(source.Next(targets[35].key) == &targets[35]);
#ifdef PS5_NATIVE
        assert(GraphicsPipelineCacheKey::comparisons == 2);
#else
        assert(GraphicsPipelineCacheKey::comparisons == 37);
#endif
    }
    // Misses never poison a valid memo; target order remains unchanged.
    assert(source.Next(GraphicsPipelineCacheKey{900}) == nullptr);
    GraphicsPipelineCacheKey::comparisons = 0;
    assert(source.Next(targets[35].key) == &targets[35]);
#ifdef PS5_NATIVE
    assert(GraphicsPipelineCacheKey::comparisons == 2);
#endif
    // Replacing the hot target and appending must preserve earlier indices.
    assert(source.Next(targets[46].key) == &targets[46]);
    for (int i = 48; i < 64; ++i) {
        targets[i].key.value = i;
        source.AddTransition(&targets[i]);
    }
    assert(source.Next(targets[46].key) == &targets[46]);
    assert(source.Next(targets[63].key) == &targets[63]);
    assert(source.Next(targets[0].key) == &targets[0]);
    GraphicsPipeline small{};
    small.key.value = -10;
    small.AddTransition(&targets[0]);
    small.AddTransition(&targets[1]);
    assert(small.Next(targets[0].key) == &targets[0]);
    assert(small.Next(targets[1].key) == &targets[1]);
    assert(small.Next(targets[2].key) == nullptr);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++ compiler missing"
with tempfile.TemporaryDirectory(prefix="encore-f07-transition-") as folder:
    path = Path(folder) / "test.cpp"
    path.write_text(cpp)
    for define in ([], ["-DPS5_NATIVE=1"]):
        for optimize in ("-O0", "-O2"):
            exe = Path(folder) / ("test-" + ("ps5" if define else "desktop") + optimize)
            subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                            optimize, *define, str(path), "-o", str(exe)],
                           capture_output=True, text=True, check=True, timeout=40)
            subprocess.run([str(exe)], check=True, timeout=15)
print("F07_GRAPHICS_TRANSITION_HOST_PASS native=1 desktop=1 O0=1 O2=1 order=1 miss=1")
