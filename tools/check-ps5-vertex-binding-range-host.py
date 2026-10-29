#!/usr/bin/env python3
"""Guard native Vulkan vertex binding count from unsigned reversed-range wrap."""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_buffer_cache.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
anchor = "void BufferCacheRuntime::BindVertexBuffers("
method = native.split(anchor, 1)[1].split(
    "\nvoid BufferCacheRuntime::BindTransformFeedbackBuffer(", 1)[0]
old = """    const u32 min_binding = (std::min)(bindings.min_index, device_max);
    const u32 max_binding = (std::min)(bindings.max_index, device_max);
    const u32 binding_count = max_binding - min_binding;
    if (binding_count == 0) {
        return;
    }"""
new = """    const u32 min_binding = (std::min)(bindings.min_index, device_max);
    const u32 max_binding = (std::min)(bindings.max_index, device_max);
    // Do not wrap a reversed binding range into a huge Vulkan binding count.
    if (max_binding <= min_binding) {
        return;
    }
    const u32 binding_count = max_binding - min_binding;"""
assert old in pinned
assert method.count(new) == 1
assert method.index(new) < method.index("boost::container::static_vector<VkBuffer,")
assert method.index(new) < method.index("ReserveNullBuffer();")
assert "F07 reject empty vertex binding ranges before cache handle resolution" in generator
assert "F07 trim vertex handles after device limit clamp" in generator
assert "python3 -B tools/check-ps5-vertex-binding-range-host.py" in workflow

tree = ast.parse(generator)
pairs = []
for node in ast.walk(tree):
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "vk_buffer_cache":
                for item in value.elts:
                    try:
                        pair = ast.literal_eval(item)
                    except (ValueError, TypeError, SyntaxError):
                        continue
                    if isinstance(pair, tuple) and len(pair) == 2:
                        pairs.append(pair)
assert pairs.count((old, new)) == 1

# Extract the actual native range clamp and early-return logic into a
# host-compiled witness. No source reimplementation of the guard.
prefix = method[method.index("    const u32 device_max ="):method.index(
    "\n#ifdef PS5_NATIVE", method.index("    const u32 device_max ="))]
assert prefix.count("return;") == 1
cpp = r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <limits>
using u32 = std::uint32_t;
struct Device {
    u32 max;
    u32 GetMaxVertexInputBindings() const {return max;}
};
struct Bindings {u32 min_index, max_index;};
struct Witness {
    Device device;
    Bindings bindings;
    u32 count=0;
    void Bind() {
__PREFIX__
        count = binding_count;
    }
};
int main() {
    auto check=[](u32 min, u32 max, u32 cap, u32 count){
        Witness w{{cap},{min,max}};
        w.Bind();
        assert(w.count==count);
    };
    check(0,4,16,4);
    check(3,5,16,2);
    check(3,30,16,13);
    check(16,30,16,0);
    check(7,7,16,0);
    check(8,4,16,0);
    check(19,10,16,0);
    check(0,2,0,0);
    check(std::numeric_limits<u32>::max(),0,16,0);
    check(0,std::numeric_limits<u32>::max(),16,16);
}
""".replace("__PREFIX__", prefix)
clang=shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang with ASan/UBSan required"
with tempfile.TemporaryDirectory(prefix="encore-vertex-bind-") as tmp:
    src=Path(tmp)/"witness.cpp";bin=Path(tmp)/"witness"
    src.write_text(cpp)
    subprocess.run([clang,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(bin)],check=True,timeout=45)
    subprocess.run([str(bin)],check=True,timeout=30)
print("VERTEX_BINDING_RANGE_HOST_PASS normal=3 clamped=2 reversed=3 empty=2")

# Execute the source-extracted guard INCLUDING the handle-creation loop.
# Reversed and clamped-empty ranges must not probe any buffer handle,
# mutate a binding or reserve a substitute NULL buffer.
whole_prefix=method[method.index("    const u32 device_max ="):
                    method.index("    if (device.IsExtExtendedDynamicStateSupported())")]
assert whole_prefix.index("if (max_binding <= min_binding)") < whole_prefix.index("buffer_handles(handle_count)")
extended=r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <limits>
#include <optional>
#include <vector>
using u32=std::uint32_t;
using VkBuffer=std::uint64_t;
constexpr VkBuffer VK_NULL_HANDLE=0;
constexpr std::uint64_t VK_WHOLE_SIZE=~std::uint64_t{0};
namespace VideoCommon {constexpr std::size_t NUM_VERTEX_BUFFERS=32;}
namespace boost {namespace container{
template<class T,std::size_t Capacity>using static_vector=std::vector<T>;
}}
struct Buffer {
  unsigned* accesses{};VkBuffer value{};
  VkBuffer Handle() const {++*accesses;return value;}
};
struct Bindings {
  u32 min_index{}, max_index{};
  std::vector<Buffer*> buffers{};
  std::vector<u32> offsets{};
  std::vector<std::uint64_t> sizes{};
  std::vector<std::uint64_t> strides{};
};
struct Device {
  u32 max_bindings{};
  bool allows_null{};
  u32 GetMaxVertexInputBindings() const{return max_bindings;}
  bool HasNullDescriptor() const{return allows_null;}
};
struct Host {
  Device device{};
  Bindings bindings{};
  std::optional<VkBuffer> null_buffer{99};
  unsigned substitute_requests{}, selected{};
  void ReserveNullBuffer(){++substitute_requests;}
  void Bind(){
""" + whole_prefix + r"""
  selected=binding_count;
  }
};
int main(){
  unsigned calls=0;
  Buffer absent{&calls,0};
  Host reversed{{16,false},{8,4,{&absent},{9},{123}}};
  reversed.Bind();
  assert(reversed.selected==0 && calls==0 && reversed.substitute_requests==0);
  assert(reversed.bindings.offsets[0]==9 && reversed.bindings.sizes[0]==123);

  Host capped{{8,false},{8,30,{&absent},{9},{123}}};
  capped.Bind();
  assert(capped.selected==0 && calls==0 && capped.substitute_requests==0);
  assert(capped.bindings.offsets[0]==9 && capped.bindings.sizes[0]==123);

  Buffer present{&calls,77};
  Host valid{{16,false},{1,3,{&present,&absent},{3,5},{200,100},{4,8}}};
  valid.Bind();
  assert(valid.selected==2 && calls==2 && valid.substitute_requests==1);
  assert(valid.bindings.offsets[0]==3 && valid.bindings.offsets[1]==0);
  assert(valid.bindings.sizes[1]==VK_WHOLE_SIZE);

  Host maxzero{{0,false},{0,4,{&absent},{4},{8}}};
  maxzero.Bind();
  assert(maxzero.selected==0 && calls==2 && maxzero.substitute_requests==0);

  // The driver exposes only two bindings of the four host entries.
  // Unused tail handles and offset/size data must remain untouched.
  Host clipped{{2,false},{0,4,{&present,&absent,&absent,&absent},
                               {11,13,17,19},{101,103,107,109},{1,2,3,4}}};
  clipped.Bind();
#ifdef PS5_NATIVE
  assert(clipped.selected==2 && calls==4 && clipped.substitute_requests==1);
  assert(clipped.bindings.offsets[2]==17 && clipped.bindings.offsets[3]==19);
  assert(clipped.bindings.sizes[2]==107 && clipped.bindings.sizes[3]==109);
  // A malformed live range must not dereference short host arrays.
  Host short_host{{4,false},{0,3,{&present},{7},{11},{4}}};
  short_host.Bind();
  assert(short_host.selected==0 && calls==4 && short_host.substitute_requests==0);
#else
  // Desktop retains its original all-handles preparation behavior.
  assert(clipped.selected==2 && calls==6 && clipped.substitute_requests==3);
  assert(clipped.bindings.offsets[2]==0 && clipped.bindings.offsets[3]==0);
  assert(clipped.bindings.sizes[2]==VK_WHOLE_SIZE);
#endif
}
"""
with tempfile.TemporaryDirectory(prefix="encore-vertex-early-") as tmp:
    src=Path(tmp)/"vertex.cpp"
    src.write_text(extended)
    for mode in ("-O0","-O2"):
        for ps5 in (False,True):
            bin=Path(tmp)/("vertex"+mode+("-ps5" if ps5 else "-desktop"))
            built=subprocess.run([clang,"-std=c++20",mode,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *(["-DPS5_NATIVE=1"] if ps5 else []),
                                  str(src),"-o",str(bin)],capture_output=True,text=True,timeout=45)
            assert built.returncode==0,(mode,ps5,built.stderr[-5000:])
            run=subprocess.run([str(bin)],capture_output=True,text=True,timeout=20)
            assert run.returncode==0,(mode,ps5,run.stderr[-5000:])
print("VERTEX_EARLY_REJECTION_HOST_PASS invalid_no_handles=1 clamped_no_null=1"
      " clamped_tail_ignored=1 malformed_rejected=1 desktop_unchanged=1 valid_handles_and_fallback=1 O0_O2=1")

# Source-extracted native transform-feedback input validation. The upstream
# version constructs the fixed-capacity vector even with invalid guest arrays.
tfb_begin="void BufferCacheRuntime::BindTransformFeedbackBuffers("
tfb_end="\nvoid BufferCacheRuntime::ReserveNullBuffer("
assert native.count(tfb_begin)==1 and native.count(tfb_end)==1
tfb_method=native[native.index(tfb_begin):native.index(tfb_end,native.index(tfb_begin))]
assert "F07 reject malformed native transform-feedback binding arrays" in generator
assert "binding_count > VideoCommon::NUM_VERTEX_BUFFERS" in tfb_method
assert "bindings.offsets.size() < binding_count" in tfb_method
assert "bindings.sizes.size() < binding_count" in tfb_method
guard_begin=tfb_method.index("#ifdef PS5_NATIVE")
guard_end=tfb_method.index("#endif",guard_begin)+len("#endif")
tfb_guard=tfb_method[guard_begin:guard_end]
assert tfb_method.index("binding_count == 0") < tfb_method.index("buffer_handles(bindings.buffers.size())")
tfb_cpp=r"""
#include <cassert>
#include <cstddef>
#include <vector>
namespace VideoCommon {constexpr std::size_t NUM_VERTEX_BUFFERS=32;}
struct HostBindings {
    std::vector<int> buffers,offsets,sizes;
};
struct Guard {
    HostBindings bindings;
    unsigned attempts{};
    void Bind() {
__TFB_GUARD__
        ++attempts;
    }
};
int main(){
    const auto check=[](std::size_t n,std::size_t off,std::size_t sz,[[maybe_unused]] bool accepted) {
        Guard g;
        g.bindings.buffers.resize(n);
        g.bindings.offsets.resize(off);
        g.bindings.sizes.resize(sz);
        g.Bind();
#ifdef PS5_NATIVE
        assert((g.attempts==1)==accepted);
#else
        assert(g.attempts==1);
#endif
    };
    check(0,0,0,false);
    check(1,1,1,true);
    check(8,8,8,true);
    check(32,32,32,true);
    check(33,33,33,false);
    check(3,2,3,false);
    check(3,3,2,false);
    check(3,4,5,true);
}
""".replace("__TFB_GUARD__",tfb_guard)
for mode in (False,True):
    for opt in ("-O0","-O2"):
        with tempfile.TemporaryDirectory(prefix="eden-f07-tfb-guard-") as folder:
            path=Path(folder)/"tfb.cpp"; exe=Path(folder)/"tfb"
            path.write_text(tfb_cpp)
            command=[clang,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                     "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                     *(['-DPS5_NATIVE=1'] if mode else []),str(path),"-o",str(exe)]
            built=subprocess.run(command,capture_output=True,text=True,timeout=45)
            assert built.returncode==0,(mode,opt,built.stderr[-3200:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert run.returncode==0,(mode,opt,run.stderr[-3200:])
print("F07_NATIVE_TFB_BINDINGS_GUARD_PASS native_empty=1 overcapacity=1 short_arrays=1 desktop_original=1 O0=1 O2=1")

# Source-extracted index fallback: preserving a stale guest offset after
# replacing the lost VkBuffer with a 4-byte null buffer is invalid Vulkan.
index_begin="void BufferCacheRuntime::BindIndexBuffer("
index_end="\nvoid BufferCacheRuntime::BindQuadIndexBuffer("
assert native.count(index_begin)==1 and native.count(index_end)==1
index_method=native[native.index(index_begin):native.index(index_end,native.index(index_begin))]
old_index="if (vk_buffer == VK_NULL_HANDLE) {"
assert index_method.count(old_index)==1
index_start=index_method.index("    "+old_index)
index_stop=index_method.index("\n    scheduler.Record(",index_start)
index_fallback=index_method[index_start:index_stop]
assert "vk_offset = 0;" in index_fallback
assert "F07 reset native null index fallback byte offset" in generator
index_cpp=r"""
#include <cassert>
#include <cstdint>
#include <memory>
using VkBuffer=std::uint64_t;
using VkDeviceSize=std::uint64_t;
constexpr VkBuffer VK_NULL_HANDLE=0;
struct Guard {
    VkBuffer vk_buffer{};
    VkDeviceSize vk_offset{};
    std::unique_ptr<VkBuffer> null_buffer;
    unsigned created{};
    void ReserveNullBuffer() {
        ++created;
        null_buffer=std::make_unique<VkBuffer>(777);
    }
    void Bind() {
__INDEX_FALLBACK__
    }
};
int main(){
    Guard missing;
    missing.vk_buffer=VK_NULL_HANDLE;
    missing.vk_offset=123456;
    missing.Bind();
    assert(missing.vk_buffer==777 && missing.created==1);
#ifdef PS5_NATIVE
    assert(missing.vk_offset==0);
#else
    assert(missing.vk_offset==123456);
#endif
    Guard valid;
    valid.vk_buffer=12;valid.vk_offset=96;
    valid.Bind();
    assert(valid.vk_buffer==12 && valid.vk_offset==96 && valid.created==0);
}
""".replace("__INDEX_FALLBACK__",index_fallback)
for mode in (False,True):
    for opt in ("-O0","-O2"):
        with tempfile.TemporaryDirectory(prefix="eden-f07-null-index-") as folder:
            path=Path(folder)/"index.cpp";exe=Path(folder)/"index"
            path.write_text(index_cpp)
            cmd=[clang,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if mode else []),str(path),"-o",str(exe)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            assert built.returncode==0,(mode,opt,built.stderr[-3600:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert run.returncode==0,(mode,opt,run.stderr[-3600:])
print("F07_NATIVE_NULL_INDEX_OFFSET_PASS native_offset_reset=1 real_index_unchanged=1 desktop_original=1 O0=1 O2=1")
