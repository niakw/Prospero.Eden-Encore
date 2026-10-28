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
assert selected.count("hot_transition_index") == 4
assert header.count("    size_t hot_transition_index{};") == 1
assert "transition_source.count(transition_next_old) != 1" in generator
assert "transition_source.replace(transition_next_old, transition_next_new, 1)" in generator
assert "transition_member_old" in generator and "transition_member_new" in generator
assert "std::vector<GraphicsPipeline*> transitions;" in header
source = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
append_begin = "void GraphicsPipeline::AddTransition(GraphicsPipeline* transition) {"
append_end = "\n\n#ifdef PS5_NATIVE\nvoid GraphicsPipeline::PreflightDescriptorScratch() {"
assert source.count(append_begin) == source.count(append_end) == 1
append_method = source[source.index(append_begin):source.index(append_end,source.index(append_begin))]
assert "transition_keys.pop_back();" in append_method
assert "F07 graphics transition append rollback" in generator
assert "F07 optional transition OOM no-throw fallback" in generator
assert "transition_keys.pop_back();\n        return;" in append_method

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <new>
#include <vector>
template <class T>
class FailPointerAppend : public std::vector<T> {
public:
    static inline bool reject_next{};
    void push_back(const T& element) {
        if (reject_next) {
            reject_next = false;
            throw std::bad_alloc{};
        }
        std::vector<T>::push_back(element);
    }
};
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
    FailPointerAppend<GraphicsPipeline*> transitions;
#ifdef PS5_NATIVE
    size_t hot_transition_index{};
#endif
""" + selected + r"""
    void AddTransition(GraphicsPipeline* other);
};
""" + append_method + r"""
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
#ifdef PS5_NATIVE
    // Reproduce a real second-vector allocation failure AFTER the key was
    // appended. The original source kept an orphaned key and Next() could
    // read transitions[index] past its end; both arrays must remain aligned.
    GraphicsPipeline resilient{};
    resilient.key.value = -12;
    resilient.AddTransition(&targets[0]);
    FailPointerAppend<GraphicsPipeline*>::reject_next = true;
    // The optional transition memo failed, but the draw path must not throw.
    // The canonical graphics-cache lookup remains available on the next draw.
    resilient.AddTransition(&targets[1]);
    assert(!FailPointerAppend<GraphicsPipeline*>::reject_next);
    assert(resilient.transition_keys.size() == resilient.transitions.size());
    assert(resilient.transition_keys.size() == 1);
    assert(resilient.Next(targets[1].key) == nullptr);
    assert(resilient.Next(targets[0].key) == &targets[0]);
    resilient.AddTransition(&targets[1]);
    assert(resilient.transition_keys.size() == resilient.transitions.size());
    assert(resilient.Next(targets[1].key) == &targets[1]);
#endif
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
print("F07_GRAPHICS_TRANSITION_HOST_PASS native=1 desktop=1 O0=1 O2=1 order=1 miss=1 oom_rollback=1 nonfatal=1")
