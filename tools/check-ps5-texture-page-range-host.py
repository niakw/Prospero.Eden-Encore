#!/usr/bin/env python3
"""Compile the actual maintained CPU/GPU image page traversals.

Pinned source/patch replay and native/non-native valid-range equivalence.
Reject zero/wrapping guest page spans on PS5; no console FPS claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/video_core/texture_cache/texture_cache_base.h").read_text()
active = (root / "vendor/encore-active/eden-backports/src/video_core/texture_cache/texture_cache_base.h").read_text()
patch = root / "headless/backports/eden-ps5-texture-page-range-guards.patch"
shipping = (root / "tools/apply-eden-backports.sh").read_text()
assert 'apply_one "$root/headless/backports/eden-ps5-texture-page-range-guards.patch"' in shipping
guard = "if (size == 0 || size - 1 > (std::numeric_limits<u64>::max)() - addr)"
trait = "std::is_same_v<std::invoke_result_t<Func, u64>, bool>"
assert active.count(guard) == 2
assert active.count(trait) == 2
assert pinned.count(guard) == 0

def method(text, name):
    start = text.index("    static void " + name + "(")
    end = text.index("\n    }\n", start) + len("\n    }\n")
    return text[start:end]

names = ("ForEachCPUPage", "ForEachGPUPage")
for name in names:
    original = method(pinned, name)
    selected = method(active, name)
    assert selected.count("#ifdef PS5_NATIVE") == 2
    assert selected.count(guard) == 1
    assert selected.count(trait) == 1
    assert selected.index(trait) < selected.index(guard) < selected.index("const u64 page_end =")
    # Both the native-only type-trait repair and the range guard must be
    # reversible into the exact pinned, non-PS5 iterator.
    trait_block = ("""#ifdef PS5_NATIVE
        // invoke_result is the trait struct, not the callback return type.
        // Respect early-stop bool callbacks after the first matching image.
        static constexpr bool RETURNS_BOOL = std::is_same_v<std::invoke_result_t<Func, u64>, bool>;
#else
        static constexpr bool RETURNS_BOOL = std::is_same_v<std::invoke_result<Func, u64>, bool>;
#endif
""")
    guard_block = ("""#ifdef PS5_NATIVE
        // A zero byte region has no pages. An overflowing exclusive end
        // cannot refer to a valid guest mapping: do not wrap into a huge
        // page scan (notably addr=0, size=0).
        if (size == 0 || size - 1 > (std::numeric_limits<u64>::max)() - addr) {
            return;
        }
#endif
""")
    assert selected.count(trait_block) == 1
    assert selected.count(guard_block) == 1
    old_trait = "        static constexpr bool RETURNS_BOOL = std::is_same_v<std::invoke_result<Func, u64>, bool>;\n"
    assert selected.replace(trait_block, old_trait).replace(guard_block, "") == original

# Apply the *real* git patch to the pinned header and verify both selected
# method bodies. The full file may have other reviewed shipping backports.
with tempfile.TemporaryDirectory(prefix="encore-texture-page-replay-") as tmp:
    stage = Path(tmp)
    target = stage / "src/video_core/texture_cache/texture_cache_base.h"
    target.parent.mkdir(parents=True)
    target.write_text(pinned)
    for command in (["git", "apply", "--check", str(patch)],
                    ["git", "apply", str(patch)]):
        done = subprocess.run(command, cwd=stage, text=True,
                              capture_output=True, timeout=20)
        assert done.returncode == 0, (command, done.stderr[-3000:])
    applied = target.read_text()
    for name in names:
        assert method(applied, name) == method(active, name)
    print("ENCORE_TEXTURE_PAGE_PINNED_PATCH_REPLAY_PASS")

code = r"""
#include <cassert>
#include <cstdint>
#include <limits>
#include <type_traits>
#include <vector>
using u64 = std::uint64_t;
using DAddr = u64;
using GPUVAddr = u64;
inline constexpr unsigned YUZU_PAGEBITS = 12;
struct PageOps {
""" + method(active, names[0]) + method(active, names[1]) + r"""
};
template<class Walk>
static void valid_cases(Walk&& walk) {
    std::vector<u64> pages;
    walk(4095,2,[&](u64 page){pages.push_back(page);});
    assert((pages == std::vector<u64>{0,1}));
    pages.clear();
    walk(4096,4096,[&](u64 page){pages.push_back(page);});
    assert((pages == std::vector<u64>{1}));
    pages.clear();
    walk(4096,4097,[&](u64 page){pages.push_back(page);});
    assert((pages == std::vector<u64>{1,2}));
    pages.clear();
    walk(0,1,[&](u64 page){pages.push_back(page);});
    assert((pages == std::vector<u64>{0}));
    pages.clear();
    walk((std::numeric_limits<u64>::max)()-3,4,
         [&](u64 page){pages.push_back(page);});
    assert(pages.size()==1);
    assert(pages[0]==(std::numeric_limits<u64>::max)()>>12);
    pages.clear();
    walk(4095,8193,[&](u64 page)->bool {pages.push_back(page);return true;});
#ifdef PS5_NATIVE
    assert((pages == std::vector<u64>{0}));
#else
    // Pinned source had an inactive BOOL_BREAK trait; the native-only fix
    // intentionally leaves the upstream traversal byte-for-byte unchanged.
    assert((pages == std::vector<u64>{0,1,2}));
#endif
}
int main() {
    valid_cases([](auto addr,auto size,auto fn) {
        PageOps::ForEachCPUPage(addr,size,fn);
    });
    valid_cases([](auto addr,auto size,auto fn) {
        PageOps::ForEachGPUPage(addr,size,fn);
    });
#ifdef PS5_NATIVE
    // Both zero-length and invalid ranges must be rejected without callback.
    // Before F03/F04, (0,0) scanned a near-infinite number of pages.
    for (auto walk : {0,1}) {
        int calls=0;
        const auto count=[&](u64){++calls;};
        auto run=[&](u64 addr,u64 size) {
            if(walk==0) PageOps::ForEachCPUPage(addr,size,count);
            else PageOps::ForEachGPUPage(addr,size,count);
        };
        run(0,0);
        run(4096,0);
        run((std::numeric_limits<u64>::max)()-3,5);
        run((std::numeric_limits<u64>::max)(),2);
        assert(calls==0);
    }
#endif
}
"""
compilers=list(dict.fromkeys(filter(None,(
    shutil.which("clang++"),shutil.which("g++"),shutil.which("c++")))))
assert compilers,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-texture-pages-host-") as tmp:
    source = Path(tmp) / "pages.cpp"
    source.write_text(code)
    for compiler in compilers:
        for opt in ("-O0","-O2"):
            for label, defines in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
                exe=Path(tmp)/(Path(compiler).name+opt+label)
                built=subprocess.run(
                    [compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all",
                     *defines,str(source),"-o",str(exe)],
                    text=True,capture_output=True,timeout=50)
                assert built.returncode==0,(compiler,opt,label,built.stderr[-5000:])
                ran=subprocess.run([str(exe)],text=True,capture_output=True,timeout=12)
                assert ran.returncode==0,(compiler,opt,label,ran.stderr[-5000:])
                print("ENCORE_TEXTURE_PAGE_RANGE_PASS",Path(compiler).name,opt,label)
