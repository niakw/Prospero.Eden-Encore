#!/usr/bin/env python3
"""F07 P0.4: compile the actual PS5 reinterpret scratch-allocation bounds.

Use source-extracted native checks for empty copies, zero extents, overflowed
3D multiplicands, and accumulated overflow; compare desktop behavior without
invoking a Vulkan device. Runtime image pixels and FC27 FPS are not measured.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
invocation="python3 -B tools/check-ps5-f07-reinterpret-image-budget-host.py"
assert invocation in fast and invocation in pre
for description in ("F07 reject empty native Vulkan reinterpret image copies",
                    "F07 validate native Vulkan reinterpret scratch byte budget"):
    assert description in generator
method_start="void TextureCacheRuntime::ReinterpretImage(Image& dst, Image& src,"
method_end="\nvoid TextureCacheRuntime::BlitImage("
assert source.count(method_start) == source.count(method_end) == 1
start=source.index(method_start)
method=source[start:source.index(method_end,start)]
early_start="#ifdef PS5_NATIVE\n    // An empty reinterpret has no image pixels"
early_end="#ifndef PS5_NATIVE\n    if (ENABLE_MSAA_RESOLVE_CONSUME)"
assert method.count(early_start)==method.count(early_end)==1
early=method[method.index(early_start):method.index(early_end)]
body_start="    const u32 img_bpp = BytesPerBlock(dst.info.format);"
body_end="    const VkImage dst_image = dst.Handle();"
assert method.count(body_start)==method.count(body_end)==1
size=method[method.index(body_start):method.index(body_end)]
assert "if (copies.empty())" in early
assert "if (total_size > max_size - bytes)" in size
assert "width > max_size / height" in size
assert "area > max_size / depth" in size
assert "volume > max_size / img_bpp" in size
assert "scratch_max = size_t{1} << (std::numeric_limits<size_t>::digits - 1)" in size
assert "if (total_size > scratch_max)" in size
assert "F07 defer native reinterpret resolve invalidation until valid allocation" in generator
assert "F07 invalidate native reinterpret resolve after scratch allocation" in generator
assert method.index("const VkBuffer copy_buffer = GetTemporaryBuffer(total_size);") < method.index(
    "#ifdef PS5_NATIVE\n    // A rejected reinterpretation does not alter")
assert method.index("InvalidateResolveShadow(dst.Handle());", method.index("const VkBuffer copy_buffer")) < method.index("scheduler.RequestOutsideRenderPassOperationContext();")
assert "F07 reject scratch sizes outside Vulkan transient buffer slots" in generator
assert size.index("#else\n    for (const auto& copy") > size.index("#ifdef PS5_NATIVE")
assert size.index("const VkBuffer copy_buffer = GetTemporaryBuffer(total_size);") > size.index("#endif")
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>
using u32=std::uint32_t;
using VkBuffer=std::size_t;
using VkImage=std::size_t;
inline constexpr bool ENABLE_MSAA_RESOLVE_CONSUME=true;
struct Extent {u32 width{},height{},depth{};};
struct ImageCopy {Extent extent{};};
struct ImageInfo {u32 format{};};
struct Image {ImageInfo info{}; VkImage Handle() const {return 73;} };
u32 BytesPerBlock(u32 format) {return format;}
struct Runtime {
    std::size_t calls{},last_size{};
    std::size_t invalidates{};
    void InvalidateResolveShadow(VkImage image) {assert(image==73);++invalidates;}
    VkBuffer GetTemporaryBuffer(std::size_t bytes) {
#ifdef PS5_NATIVE
        assert(bytes!=0);
#endif
        ++calls;
        last_size=bytes;
        return bytes;
    }
    void ReinterpretImage(Image& dst,const std::vector<ImageCopy>& copies) {
#ifndef PS5_NATIVE
        if (ENABLE_MSAA_RESOLVE_CONSUME) InvalidateResolveShadow(dst.Handle());
#endif
__SOURCE_EMPTY_GUARD__
__SOURCE_SIZE_GUARD__
        static_cast<void>(copy_buffer);
    }
};
int main() {
    Image normal{{4}};
    Runtime empty;
    empty.ReinterpretImage(normal,{});
#ifdef PS5_NATIVE
    assert(empty.calls==0 && empty.invalidates==0);
#else
    assert(empty.calls==1 && empty.last_size==0);
#endif
    Runtime valid;
    valid.ReinterpretImage(normal,{{{4,5,1}},{{4,1,2}}});
    assert(valid.calls==1 && valid.last_size==112);
    assert(valid.invalidates==1);
    Image invalid_format{{0}};
    Runtime invalid;
    invalid.ReinterpretImage(invalid_format,{{{4,5,1}}});
#ifdef PS5_NATIVE
    assert(invalid.calls==0 && invalid.invalidates==0);
#endif
    for (ImageCopy copy : {ImageCopy{{0,5,1}},ImageCopy{{4,0,1}},
                           ImageCopy{{4,5,0}}}) {
        Runtime zero;
        zero.ReinterpretImage(normal,{copy});
#ifdef PS5_NATIVE
        assert(zero.calls==0 && zero.invalidates==0);
#endif
    }
    const u32 max=(std::numeric_limits<u32>::max)();
    Runtime product;
    product.ReinterpretImage(normal,{{{max,max,max}}});
#ifdef PS5_NATIVE
    assert(product.calls==0 && product.invalidates==0);
#endif
    // A positive, non-overflowing size above the last scratch-array slot
    // must also be rejected before GetTemporaryBuffer can index past it.
    Image one_byte{{1}};
    Runtime above_slot;
    above_slot.ReinterpretImage(one_byte,{{{max,max,1}}});
#ifdef PS5_NATIVE
    assert(above_slot.calls==0 && above_slot.invalidates==0);
#endif
    // Keep an independent accumulative overflow witness in the source;
    // the scratch slot ceiling normally rejects this sequence even earlier.
    Runtime aggregate;
    aggregate.ReinterpretImage(one_byte,{{{max,max,1}},{{max,max,1}}});
#ifdef PS5_NATIVE
    assert(aggregate.calls==0 && aggregate.invalidates==0);
#endif
}
""".replace("__SOURCE_EMPTY_GUARD__",early).replace("__SOURCE_SIZE_GUARD__",size)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"F07 reinterpret scratch witness needs C++20 compiler"
with tempfile.TemporaryDirectory(prefix="eden-f07-vulkan-reinterpret-") as folder:
    path=Path(folder)/"reinterpret.cpp"
    path.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            binary=Path(folder)/("reinterpret"+opt[1:]+("-ps5" if native else "-desktop"))
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),str(path),"-o",str(binary)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            assert built.returncode==0,(native,opt,built.stderr[-6000:])
            ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-6000:])
print("F07_REINTERPRET_SCRATCH_BOUNDS_PASS native_empty=1 zero_extents=1 invalid_format=1 overflow_product=1 overflow_sum=1 scratch_slot_ceiling=1 invalid_resolve_untouched=1 valid=1 desktop_original=1 O0=1 O2=1")
