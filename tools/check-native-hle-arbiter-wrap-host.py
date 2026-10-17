#!/usr/bin/env python3
"""Host UBSan witness for 32-bit guest address-arbiter counter boundaries.

Compile the actual arithmetic expressions extracted from pinned and maintained
source, verify all four overflow cases fail under UBSan before the fix, and
verify exact 32-bit wrapping plus ordinary values after the fix. This is not
a full guest scheduler or console execution test.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
original = (root / "vendor/sources/eden/src/core/hle/kernel/k_address_arbiter.cpp").read_text()
native = (root / "vendor/encore-active/eden-threading/src/core/hle/kernel/k_address_arbiter.cpp").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
module = (root / "vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
assert "python3 -B tools/check-native-hle-arbiter-wrap-host.py" in workflow
assert "native-hle-overrides.cmake" in cmake
assert "k_address_arbiter.cpp" in module
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler

def expressions(source):
    decrement = re.findall(r"const s32 decrement_value = (.*?);", source)
    assert len(decrement) == 1
    modifications = re.findall(r"new_value = (.*?);", source)
    assert len(modifications) == 5, modifications
    assert modifications[1] == modifications[4]  # Both no-waiter increments.
    arg = source.split("Result KAddressArbiter::SignalAndIncrementIfEqual(", 1)[1].split(
        "Result KAddressArbiter::SignalAndModifyByWaitingCountIfEqual(", 1)[0]
    marker = "std::addressof(user_value), addr, value,"
    assert arg.count(marker) == 1
    suffix = arg.split(marker, 1)[1]
    stop = suffix.index("),\n                 ResultInvalidCurrentMemory")
    # Stop belongs to UpdateIfEqual( ... ); nested casts are inside the fragment.
    update_arg = suffix[:stop].strip()
    assert re.sub(r"\s+", "", update_arg) == re.sub(r"\s+", "", modifications[1])
    return decrement[0], modifications[1], modifications[2], modifications[0], update_arg

assert expressions(original) == (
    "current_value - 1", "value + 1", "value - 1", "value - 2", "value + 1"
)

template = r"""
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <limits>
using u32 = std::uint32_t;
using s32 = std::int32_t;
s32 Decrement(s32 current_value) {
    const s32 decrement_value = EXPR_DECREMENT;
    return decrement_value;
}
s32 Increment(s32 value) {
    s32 new_value = EXPR_INCREMENT;
    return new_value;
}
s32 SubOne(s32 value) {
    s32 new_value = EXPR_SUBONE;
    return new_value;
}
s32 SubTwo(s32 value) {
    s32 new_value = EXPR_SUBTWO;
    return new_value;
}
s32 UpdateCallIncrement(s32 value) {
    return EXPR_CALL_INCREMENT;
}
int main(int argc, char** argv) {
    assert(argc == 2);
    volatile s32 hi = std::numeric_limits<s32>::max();
    volatile s32 lo = std::numeric_limits<s32>::min();
    switch (std::atoi(argv[1])) {
        case 0: assert(Decrement(lo) == hi); break;
        case 1: assert(Increment(hi) == lo && UpdateCallIncrement(hi) == lo); break;
        case 2: assert(SubOne(lo) == hi); break;
        case 3: assert(SubTwo(lo) == hi - 1); break;
        case 4: assert(Decrement(10) == 9 && Increment(10) == 11
            && SubOne(10) == 9 && SubTwo(10) == 8 && UpdateCallIncrement(10) == 11); break;
        default: return 10;
    }
}
"""
with tempfile.TemporaryDirectory(prefix="encore-arbiter-wrap-") as d:
    temp = Path(d)
    for label, source, fixed in (("pinned", original, False), ("native", native, True)):
        exprs = expressions(source)
        code = template
        keys = ("EXPR_DECREMENT", "EXPR_INCREMENT", "EXPR_SUBONE",
                "EXPR_SUBTWO", "EXPR_CALL_INCREMENT")
        for name, expression in zip(keys, exprs):
            assert code.count(name) == 1
            code = code.replace(name, expression)
        cpp = temp / (label + ".cpp")
        exe = temp / label
        cpp.write_text(code)
        subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined",
                        "-fno-sanitize-recover=undefined",
                        str(cpp), "-o", str(exe)], check=True, timeout=30)
        for mode in range(5):
            result = subprocess.run([str(exe), str(mode)], capture_output=True,
                                    text=True, timeout=10)
            if not fixed and mode < 4:
                assert result.returncode != 0, (label, mode, result.stdout, result.stderr)
                assert "runtime error: signed integer overflow" in result.stderr, (
                    label, mode, result.stderr)
            else:
                assert result.returncode == 0, (label, mode, result.stdout, result.stderr)
        print(("NATIVE_ARBITER_WRAP_UBSAN_PASS" if fixed else
               "PINNED_ARBITER_SIGNED_OVERFLOW_UBSAN_WITNESS_PASS"))
print("ARBITER_COUNTER_HOST_ONLY_NO_CONSOLE_OR_FREEZE_PROOF")
