#!/usr/bin/env python3
"""Source-selected native JIT no-op invalidation must not alter RX/RW protections."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64/emit_x64_native.cpp").read_text()
host = (root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64/emit_x64_host.cpp").read_text()
key = "void EmitX64::InvalidateBasicBlocks("
assert native.count(key) == host.count(key) == 1
def method(source):
    tail = source.split(key, 1)[1]
    return key + tail.split("\n}\n", 1)[0] + "\n}"
body = method(native)
assert "if (locations.empty()) return;" in body
assert body.index("if (locations.empty()) return;") < body.index("code.EnableWriting();")
assert "code.DisableWriting();" in body
assert body.count("Unpatch(descriptor);") == 1
assert body.count("block_descriptors.erase(it);") == 1
assert "if (locations.empty()) return;" not in method(host)

fixture = r"""
#include <cassert>
#include <cstdint>
#include <unordered_map>
#include <unordered_set>
namespace IR { using LocationDescriptor = std::uint64_t; }
namespace Common {
template<class T> using unordered_set = std::unordered_set<T>;
}
struct Code {
    unsigned enables{}, disables{};
    void EnableWriting(){++enables;}
    void DisableWriting(){++disables;}
};
struct EmitX64 {
    Code code;
    std::unordered_map<IR::LocationDescriptor,unsigned> block_descriptors;
    unsigned unpatches{};
    void Unpatch(IR::LocationDescriptor){++unpatches;}
    void InvalidateBasicBlocks(const ::Common::unordered_set<IR::LocationDescriptor>& locations);
};
__ACTUAL_METHOD__
int main(){
    EmitX64 j;
    j.block_descriptors.insert({7,1});
    j.InvalidateBasicBlocks({});
    assert(j.code.enables==0 && j.code.disables==0);
    assert(j.block_descriptors.size()==1 && j.unpatches==0);
    // A nonempty set with both known and unknown descriptors still
    // enters the original patch path and seals it once.
    j.InvalidateBasicBlocks({7,9});
    assert(j.code.enables==1 && j.code.disables==1);
    assert(j.unpatches==1 && j.block_descriptors.empty());
    j.InvalidateBasicBlocks({});
    assert(j.code.enables==1 && j.code.disables==1);
    j.block_descriptors.insert({15,1});
    j.InvalidateBasicBlocks({15});
    assert(j.code.enables==2 && j.code.disables==2);
    assert(j.unpatches==2 && j.block_descriptors.empty());
}
""".replace("__ACTUAL_METHOD__", body)
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-empty-block-invalid-") as folder:
    cpp=Path(folder)/"invalid.cpp"
    cpp.write_text(fixture)
    for opt in ("-O0","-O2"):
        exe=Path(folder)/("invalid"+opt)
        subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined",str(cpp),"-o",str(exe)],check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=20)
        print("NATIVE_JIT_EMPTY_INVALIDATION_PASS",opt)
