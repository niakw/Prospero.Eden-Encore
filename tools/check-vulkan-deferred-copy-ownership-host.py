#!/usr/bin/env python3
"""Real GPU copy captures + scheduler chunks: allocation cost and delayed ownership."""
from pathlib import Path
import ast
import hashlib
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
active = ROOT / 'vendor/encore-active/eden-vulkan'
tree = ast.parse((ROOT / 'tools/prepare-vulkan-port.py').read_text())
edits = next(ast.literal_eval(n.value) for n in tree.body
             if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
             t.id == 'deferred_copy_edits' for t in n.targets))
probes = next(ast.literal_eval(n.value) for n in tree.body
              if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
              t.id == 'probes' for t in n.targets))
# F04 deliberately changed the selected Vulkan upload barrier. Preserve the
# original pre-deferred-copy fingerprint by undoing that separately reviewed
# edit as well. Import its exact transform from the pinned-fork oracle rather
# than copying an evolving SHA into this unrelated ownership regression.
oracle = ast.parse((ROOT / 'tools/check-vendored-vulkan-fork.py').read_text())
upload_nodes = [n for n in ast.walk(oracle)
                if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == 'upload_deltas'
                    for t in n.targets)]
assert len(upload_nodes) == 1
upload_deltas = ast.literal_eval(upload_nodes[0].value)
# Four transfer-barrier updates, the native BCn-3D constructor fix and the
# two explicit unavailable-pass deltas. Undo all seven for the historical SHA.
# Keep the historical fingerprint strict; do not recompute it from active code.
assert len(upload_deltas) == 7
assert sum("VK_KHR_image_format_list" in current for _, current in upload_deltas) == 1

# This historical SHA is checked on the exact pre-deferred-copy source.
# Reconstruct it by also undoing later F07 changes to the same native module,
# read from their strict generator transforms. Do not update the SHA just
# because the shipping buffer source gained independently reviewed patches.
f07_copy_labels = (
    'F07 avoid barrier-free empty Vulkan buffer copies',
    'F07 skip zero-sized Vulkan buffer fill',
    'F07 reject empty vertex binding ranges before cache handle resolution',
    'F07 trim vertex handles after device limit clamp',
)
f07_buffer_deltas = []
for statement in tree.body:
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        continue
    call = statement.value
    if not isinstance(call.func, ast.Name) or call.func.id != 'apply_reviewed_delta':
        continue
    if len(call.args) != 4:
        continue
    try:
        path, old, new, label = (ast.literal_eval(arg) for arg in call.args)
    except (ValueError, TypeError, SyntaxError):
        continue
    if path == 'vk_buffer_cache_cost.cpp' and label in f07_copy_labels:
        f07_buffer_deltas.append((old, new, label))
assert tuple(label for _, _, label in f07_buffer_deltas) == f07_copy_labels
assert all(old != new and old and new for old, new, _ in f07_buffer_deltas)

tick_snapshot = [(old, new) for old, new in probes['vk_buffer_cache']
                 if "BufferCacheRuntime::TickFrame(" in new]
assert len(tick_snapshot) == 1
before_blobs = {'vk_buffer_cache': '626873afa8918cf40264d8650489c7a2e2a628fa',
                'vk_texture_cache': 'fdc8267b6b02f841dc435cfcc3a7b68bffa80750'}
captures = []
for module, changes in edits.items():
    current = (active / (module + '_cost.cpp')).read_text()
    previous = current
    for old, new, count in reversed(changes):
        assert previous.count(new) == count, (module, new)
        previous = previous.replace(new, old)
    if module == 'vk_texture_cache':
        # Upload synchronization changed after the deferred-copy optimization.
        # Undo it before verifying the original historical blob so the fixed
        # fingerprint continues to detect unrelated bytes or source drift.
        for pinned_fragment, reviewed_fragment in reversed(upload_deltas):
            assert previous.count(reviewed_fragment) == 1, (
                "reviewed Vulkan image upload barrier moved", reviewed_fragment)
            previous = previous.replace(reviewed_fragment, pinned_fragment)
    if module == 'vk_buffer_cache':
        # Undo the newer no-op-copy and vertex-range deltas in reverse
        # application order, using their reviewed exact source spans.
        # A missing or duplicated span must fail the fingerprint check.
        for source_before, source_after, label in reversed(f07_buffer_deltas):
            assert previous.count(source_after) == 1, (
                "native F07 buffer delta drift", label)
            previous = previous.replace(source_after, source_before, 1)
        # This later, independent frame-snapshot optimization must not
        # invalidate the historical fingerprint of deferred-copy ownership.
        snapshot_before, snapshot_after = tick_snapshot[0]
        assert previous.count(snapshot_after) == 1
        previous = previous.replace(snapshot_after, snapshot_before)
    encoded = previous.encode()
    assert hashlib.sha1(b'blob ' + str(len(encoded)).encode() + b'\0' + encoded).hexdigest() == before_blobs[module]
    pattern = r'\[([^\[\]]*\bvk_copies\b[^\[\]]*)\]\('
    old_captures = list(re.finditer(pattern, previous))
    new_captures = list(re.finditer(pattern, current))
    assert len(old_captures) == len(new_captures) == (2 if module == 'vk_buffer_cache' else 5)
    for index, (old, new) in enumerate(zip(old_captures, new_captures)):
        nested = 'buffers =' in new.group(1)
        kind = 'VkBufferCopy' if module == 'vk_buffer_cache' else 'VkBufferImageCopy' if nested or index else 'VkImageCopy'
        captures.append((old.group(1), new.group(1), kind, nested, module == 'vk_buffer_cache' and index == 0))

header = (active / 'include/video_core/renderer_vulkan/vk_scheduler.h').read_text()
chunk = header[header.index('    class Command {'):header.index('    struct State {')]
# Fixture access sets the tail offset to force a failed Record before retry;
# the actual allocation, move, execution and destruction bodies stay intact.
chunk = chunk.replace('private:', 'public:')
record_start = '    template <typename T>\n        requires std::is_invocable_v<T, vk::CommandBuffer, vk::CommandBuffer>'
record = header[header.index(record_start):header.index('    /// Returns the current command buffer tick.')]
scheduler = (active / 'vulkan_scheduler.cpp').read_text()
begin = scheduler.index('void Scheduler::CommandChunk::ExecuteAll(')
execute = scheduler[begin:scheduler.index('\n}\n', begin) + 3]
cpp = r'''
#include <vulkan/vulkan_core.h>
#include <boost/container/small_vector.hpp>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <new>
#include <type_traits>
#include <utility>
using u8 = std::uint8_t; using u64 = std::uint64_t;
static unsigned allocations;
void* operator new(std::size_t n) {
    ++allocations;
    if (void* p = std::malloc(n)) return p;
    throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
namespace Common { std::size_t AlignUp(std::size_t n, std::size_t a) { return (n + a - 1) & ~(a - 1); } }
template<class Range> u64 Digest(const Range& values) {
    u64 hash = 0;
    for (const auto& value : values) {
        if constexpr (requires { value.begin(); }) hash = hash * 131 + Digest(value);
        else {
            const auto* bytes = reinterpret_cast<const u8*>(&value);
            for (std::size_t i = 0; i < sizeof(value); ++i) hash = hash * 131 + bytes[i];
        }
    }
    return hash;
}
namespace vk { struct CommandBuffer {
    u64* observed;
    template<class R> void Check(const R& values) const { *observed = Digest(values); }
}; }
namespace Vulkan {
class Scheduler {
public:
CHUNK
RECORD
    std::array<CommandChunk, 2> chunks;
    CommandChunk* chunk = &chunks[0];
    unsigned switches = 0;
    void DispatchWork() { assert(++switches == 1); chunk = &chunks[1]; }
    void ForceRollover() { chunks[0].command_offset = 0x8000 - 1; }
    void Drain(u64& observed) {
        for (auto& c : chunks) c.ExecuteAll({&observed}, {&observed});
        assert(chunks[0].Empty() && chunks[1].Empty());
    }
};
EXECUTE
}
template<class T> void Fill(T& value, unsigned seed) {
    auto* bytes = reinterpret_cast<u8*>(&value);
    for (std::size_t i = 0; i < sizeof(T); ++i) bytes[i] = static_cast<u8>(seed + i);
}
CASES
int main() {
CALLS
    std::puts("DEFERRED_COPY_OWNERSHIP_PASS sites=7 delayed=1 chunk_rollover=1 chunk_reuse=1 sanitizers=ASan,UBSan");
}
'''
cases, calls = [], []
for index, (old, new, kind, nested, upload) in enumerate(captures):
    for label, capture in (('previous', old), ('active', new)):
        payload = f'boost::container::small_vector<{kind}, {8 if kind == "VkBufferCopy" else 16}>'
        container = f'boost::container::small_vector<{payload}, 8>' if nested else payload
        fill = 'for (unsigned i = 0; i < 32; ++i) { auto& v = vk_copies.emplace_back(); for (unsigned j = 0; j < 64; ++j) { auto& p = v.emplace_back(); Fill(p, i + j); } }' if nested else 'for (unsigned i = 0; i < 128; ++i) { auto& p = vk_copies.emplace_back(); Fill(p, i); }'
        names = [part.strip().split('=', 1)[0].strip() for part in capture.split(',')]
        use = ' '.join('(void)' + n + ';' for n in names if n != 'vk_copies')
        method = 'RecordWithUploadBuffer' if upload else 'Record'
        signature = 'vk::CommandBuffer cmdbuf, vk::CommandBuffer' if upload else 'vk::CommandBuffer cmdbuf'
        cases.append(f'''
void {label}_{index}() {{
    Vulkan::Scheduler scheduler;
    scheduler.ForceRollover();
    u64 expected = 0, observed = 0;
    unsigned copies_allocated = 0;
    {{
        {container} vk_copies;
        {fill}
        expected = Digest(vk_copies);
        [[maybe_unused]] VkBuffer src_buffer{{}}, dst_buffer{{}};
        [[maybe_unused]] VkImage dst_image{{}}, src_image{{}}, vk_image{{}}, temp_vk_image{{}};
        [[maybe_unused]] const VkImage* original_image = &vk_image;
        [[maybe_unused]] VkImageAspectFlags aspect_mask{{}}, vk_aspect_mask{{}};
        [[maybe_unused]] bool barrier = true, was_initialized = true;
        [[maybe_unused]] boost::container::small_vector<VkBuffer, 8> buffers_vector(32);
        const auto before = allocations;
        scheduler.{method}([{capture}]({signature}) {{ {use} cmdbuf.Check(vk_copies); }});
        copies_allocated = allocations - before;
        vk_copies.clear(); // caller storage is gone before deferred execution
    }}
    assert(scheduler.switches == 1);
    scheduler.Drain(observed);
    assert(observed == expected);
    assert(copies_allocated {'>' if label == 'previous' else '=='} 0);
    scheduler.Record([](vk::CommandBuffer cmdbuf) {{ const std::array<u64, 1> value{{91}}; cmdbuf.Check(value); }});
    scheduler.Drain(observed);
    assert(observed == Digest(std::array<u64, 1>{{91}}));
    std::printf("DEFERRED_COPY site={index} mode={label} capture_allocations=%u\\n", copies_allocated);
}}
''')
        calls.append(f'    {label}_{index}();')
cpp = cpp.replace('CHUNK', chunk).replace('RECORD', record).replace('EXECUTE', execute)
cpp = cpp.replace('CASES', '\n'.join(cases)).replace('CALLS', '\n'.join(calls))
compiler = shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
boost = ROOT / 'vendor/sources/eden-cpm/boost/boost-1.90.0'
includes = ['-I' + str(p) for p in sorted(boost.glob('libs/*/include'))]
includes.append('-I' + str(ROOT / 'vendor/sources/eden-cpm/vulkanheaders/v1.4.345/include'))
with tempfile.TemporaryDirectory(prefix='encore-deferred-copy-') as temp:
    unit, binary = Path(temp) / 'main.cpp', Path(temp) / 'copy'
    unit.write_text(cpp)
    subprocess.run([compiler, '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-DPS5_NATIVE=1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    *includes, str(unit), '-o', str(binary)], check=True, timeout=90)
    subprocess.run([str(binary)], check=True, timeout=30)
print('DEFERRED_COPY_HOST_ONLY GPU_completion_and_PS5_FPS=unverified')
