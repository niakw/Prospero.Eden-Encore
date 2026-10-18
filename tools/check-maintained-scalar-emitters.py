#!/usr/bin/env python3
"""Prove the scalar backend’s two maintained units match retired CMake writes."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
base=root/"vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64"
active=root/"vendor/encore-active/eden-core/src/dynarmic/backend/x64"
selector=(root/"headless/scalar-memory.cmake").read_text()
edits=json.loads(r'''[[["    // TODO: DefineValue directly on Argument for index == 0\n\n    const Xbyak::Reg32 dest = ctx.reg_alloc.ScratchGpr(code).cvt32();","    if (index == 0) {\n        // Scratch ownership preserves any still-live full vector.\n        const auto result = ctx.reg_alloc.UseScratchXmm(code, args[0]);\n        ctx.reg_alloc.DefineValue(code, inst, result);\n        return;\n    }\n\n    const Xbyak::Reg32 dest = ctx.reg_alloc.ScratchGpr(code).cvt32();",1],["        // TODO: DefineValue directly on Argument for index == 0\n        const Xbyak::Reg64 dest = ctx.reg_alloc.ScratchGpr(code).cvt64();\n        auto const source = ctx.reg_alloc.UseXmm(code, args[0]);\n        code.movq(dest, source);\n        ctx.reg_alloc.DefineValue(code, inst, dest);","        // Scratch ownership preserves any still-live full vector.\n        const auto result = ctx.reg_alloc.UseScratchXmm(code, args[0]);\n        ctx.reg_alloc.DefineValue(code, inst, result);",1]],[["void EmitX64::EmitZeroExtendWordToLong(EmitContext& ctx, IR::Inst* inst) {\n    auto args = ctx.reg_alloc.GetArgumentInfo(inst);","void EmitX64::EmitZeroExtendWordToLong(EmitContext& ctx, IR::Inst* inst) {\n    auto args = ctx.reg_alloc.GetArgumentInfo(inst);\n    if (args[0].IsInXmm(ctx.reg_alloc) && code.HasHostFeature(HostFeature::SSE41)) {\n        const auto result = ctx.reg_alloc.UseScratchXmm(code, args[0]);\n        code.pmovzxdq(result, result); // U64 consumes only the zero-extended low word.\n        ctx.reg_alloc.DefineValue(code, inst, result);\n        return;\n    }",1]]]''')
for filename,changes in (("emit_x64_vector.cpp",edits[0]),("emit_x64_data_processing.cpp",edits[1])):
    content=(base/filename).read_text()
    for old,new,count in changes:
        assert content.count(old)==count, ("pinned scalar backend changed",filename,old[:60])
        content=content.replace(old,new)
    assert (active/filename).read_text()==content, ("maintained scalar emitter differs",filename)
assert 'list(APPEND jit_sources "${EDEN_MAINTAINED_SCALAR_BACKEND}/emit_x64_${unit}.cpp")' in selector
assert "write_derived(" not in selector
assert 'file(READ "${EDEN_SCALAR_INPUT_DIR}/scalar-memory-${lower}.inc" scalar_access)' not in selector
for variant in ("standard", "checked"):
    compiled = (active / f"emit_x64_memory_{variant}.cpp.inc").read_text()
    for direction in ("read", "write"):
        oracle = (root / f"vendor/encore-active/eden-core/dynarmic/scalar/scalar-memory-{direction}.inc").read_text()
        assert oracle in compiled
assert "set(memory_source" not in selector
print("VENDOR_MAINTAINED_SCALAR_EMITTERS_PARITY_PASS: exact 3 edits, 2 compiled units")
