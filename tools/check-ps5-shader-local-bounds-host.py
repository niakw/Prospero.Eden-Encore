#!/usr/bin/env python3
"""Actual pinned and maintained scratch IR helpers under a Clang ASan/UBSan mock."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
pinned=(root/"vendor/sources/eden/src/shader_recompiler/frontend/maxwell/translate/impl/load_store_local_shared.cpp").read_text()
active=(root/"vendor/encore-active/eden-shader/src/shader_recompiler/frontend/maxwell/translate/impl/load_store_local_shared.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
ci=(root/".github/workflows/encore-core-preflight.yml").read_text()
marker="IR::U32 LoadLocal(TranslatorVisitor& v,"
end="\n} // Anonymous namespace"
assert pinned.count(marker)==active.count(marker)==1
assert active.count("IR::U1 LocalInBounds(")==1
assert active.count("void WriteLocal(TranslatorVisitor& v,")==1
assert "v.ir.LoadLocal(safe_word_offset)" in active
assert "v.ir.WriteLocal(safe_word_offset, safe_value)" in active
assert "local_size == 0 || (offset.IsImmediate() && offset.U32() >= local_size)" in active
stl=active.split("void TranslatorVisitor::STL(u64 insn) {",1)[1].split("\nvoid TranslatorVisitor::STS(",1)[0]
assert stl.count("WriteLocal(*this,")==4
assert "ir.WriteLocal(" not in stl and "ir.LoadLocal(" not in stl
assert 'list(REMOVE_ITEM eden_shader_sources "frontend/maxwell/translate/impl/load_store_local_shared.cpp")' in cmake
assert 'list(APPEND eden_shader_sources "' in cmake
assert "check-ps5-shader-local-bounds-host.py" in ci

def method(src):
    first=src.index(marker if src == pinned else "IR::U1 LocalInBounds(")
    return src[first:src.index(end,first)]

template=r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <stdexcept>
using u32=std::uint32_t;
namespace IR {
struct Value32 {
    u32 value{};
    bool immediate{};
    bool IsImmediate() const {return immediate;}
    u32 U32() const {return value;}
};
using U32=Value32;
struct U1 {bool value{};};
struct IREmitter {
    std::array<u32,8> memory{11,22,33,44,55,66,77,88};
    u32 reads{},writes{};
    U32 Imm32(u32 n){return {n,true};}
    U1 ILessThan(U32 a,U32 b,bool){return {a.value<b.value};}
    U32 Select(U1 cond,U32 a,U32 b){return cond.value?a:b;}
    U32 LoadLocal(U32 index){++reads; return {memory.at(index.value),false};}
    void WriteLocal(U32 index,U32 value){++writes;memory.at(index.value)=value.value;}
};
}
struct TranslatorVisitor {
    struct Environment {u32 bytes{16};u32 LocalMemorySize() const{return bytes;}} env;
    IR::IREmitter ir;
};
__METHOD__
int main() {
    TranslatorVisitor v;
    auto dyn=[](u32 x){return IR::U32{x,false};};
    auto imm=[](u32 x){return IR::U32{x,true};};
    assert(LoadLocal(v,dyn(3),dyn(12)).value==44);
#ifdef PINNED_UNSAFE
    bool throws=false;
    try {(void)LoadLocal(v,dyn(7),dyn(28));}
    catch(const std::out_of_range&){throws=true;}
    assert(throws);
#else
    assert(LoadLocal(v,dyn(7),dyn(28)).value==0);
    assert(LoadLocal(v,imm(7),imm(28)).value==0);
    assert(LoadLocal(v,dyn(3),dyn(0xFFFFFFFC)).value==0);
    WriteLocal(v,dyn(2),dyn(8),imm(999));
    assert(v.ir.memory[2]==999);
    WriteLocal(v,imm(3),imm(12),imm(777));
    assert(v.ir.memory[3]==777);
    const auto before=v.ir.memory;
    WriteLocal(v,dyn(7),dyn(28),imm(111));
    assert(v.ir.memory==before);
    WriteLocal(v,imm(4),imm(16),imm(321));
    assert(v.ir.memory==before);
    v.env.bytes=0;
    const auto r=v.ir.reads,w=v.ir.writes;
    assert(LoadLocal(v,dyn(0),dyn(0)).value==0);
    WriteLocal(v,dyn(0),dyn(0),imm(888));
    assert(v.ir.reads==r && v.ir.writes==w);
    assert(v.ir.memory==before);
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "Clang required for bounds regression"
with tempfile.TemporaryDirectory(prefix="encore-shader-local-") as folder:
    for name,src,flags in (("pinned",pinned,["-DPINNED_UNSAFE"]),("fixed",active,[])):
        cpp=Path(folder)/(name+".cpp")
        exe=Path(folder)/name
        cpp.write_text(template.replace("__METHOD__",method(src)))
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
            "-fsanitize=address,undefined","-fno-sanitize-recover=all",
            *flags,str(cpp),"-o",str(exe)],check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=30)
print("SHADER_LOCAL_BOUNDS_HOST_PASS pinned_bad_load=1 dynamic_guard=1 immediate_tail=1 store_preserve=1 zero_scratch=1")
