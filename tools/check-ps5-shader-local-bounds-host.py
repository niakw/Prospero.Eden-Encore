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
assert active.count("const u32 max_start{byte_advance < local_size ? local_size - byte_advance : 0};") == 2
assert active.count("LocalInBounds(v, offset, max_start)") == 2
ldl=active.split("void TranslatorVisitor::LDL(u64 insn) {",1)[1].split("\nvoid TranslatorVisitor::LDS(",1)[0]
assert "LoadLocal(*this, sub_word_offset, offset, static_cast<u32>(i * 4))" in ldl
assert "ir.IAdd(offset, ir.Imm32(i * 4))" not in ldl
stl=active.split("void TranslatorVisitor::STL(u64 insn) {",1)[1].split("\nvoid TranslatorVisitor::STS(",1)[0]
assert stl.count("WriteLocal(*this,")==4
assert "WriteLocal(*this, ir.IAdd(word_offset, ir.Imm32(i)), offset, X(reg + i)," in stl
assert "ir.IAdd(offset, ir.Imm32(i * 4))" not in stl
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
    std::array<u32,4> memory{11,22,33,44};
    u32 reads{},writes{};
    U32 Imm32(u32 n){return {n,true};}
    U1 ILessThan(U32 a,U32 b,bool){return {a.value<b.value};}
    U32 Select(U1 cond,U32 a,U32 b){return cond.value?a:b;}
    U32 LoadLocal(U32 index){++reads; return {memory.at(index.value),false};}
    void WriteLocal(U32 index,U32 value){++writes;memory.at(index.value)=value.value;}
    U32 IAdd(U32 a,U32 b){return {static_cast<u32>(a.value+b.value),a.immediate && b.immediate};}
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
    [[maybe_unused]] auto imm=[](u32 x){return IR::U32{x,true};};
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
    // A negative byte offset and its next word can wrap to zero, exactly
    // matching scratch word 0: this is the old unsafe multiword call pattern.
    constexpr u32 outside=0xFFFFFFFCu;
    assert(static_cast<u32>(outside + 4u)==0u);
    assert(v.ir.memory[0]==11);
    assert(LoadLocal(v,dyn(0),dyn(static_cast<u32>(outside+4u))).value==11);
    // Pass the ORIGINAL byte offset and the word's advance instead.
    // Neither the read nor the store can now alias scratch word 0.
    const auto reads_before=v.ir.reads, writes_before=v.ir.writes;
    assert(LoadLocal(v,dyn(0),dyn(outside),4).value==0);
    assert(LoadLocal(v,imm(0),imm(outside),4).value==0);
    WriteLocal(v,dyn(0),dyn(outside),imm(555),4);
    WriteLocal(v,imm(0),imm(outside),imm(555),4);
    assert(v.ir.memory==before);
    // Dynamic masked operations still read/rewrite valid word zero; they
    // must preserve its VALUE, not skip the modeled memory instructions.
    assert(v.ir.writes==writes_before+1);
    assert(v.ir.reads==reads_before+2);
    // A word whose base starts in bounds but whose tail crosses 16 bytes.
    assert(LoadLocal(v,dyn(0),dyn(12),4).value==0);
    WriteLocal(v,dyn(0),dyn(12),imm(456),4);
    assert(v.ir.memory==before);
    // Positive controls: a second and fourth word still work when they fit.
    assert(LoadLocal(v,dyn(3),dyn(8),4).value==777);
    WriteLocal(v,dyn(3),dyn(8),imm(654),4);
    assert(v.ir.memory[3]==654);
    v.ir.memory[3]=777;
    assert(LoadLocal(v,dyn(3),dyn(0),12).value==777);
    assert(LoadLocal(v,dyn(0),dyn(0),16).value==0);
    WriteLocal(v,dyn(0),dyn(0),imm(666),16);
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
print("SHADER_LOCAL_BOUNDS_HOST_PASS pinned_bad_load=1 dynamic_guard=1 immediate_tail=1 store_preserve=1 zero_scratch=1 tail_wrap=1 tail_cross=1 tail_inrange=1")
