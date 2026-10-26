#!/usr/bin/env python3
"""Source-only guard for the ONE PS5 release's sparse native JIT and packages.

The legacy all-on fixture name is retained for workflow references, but it
MUST refuse alternate developer builds and dense/native JIT selection.
"""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
read=lambda name:(root/name).read_text("utf-8")
workflow=read(".github/workflows/build-040-zbic.yml")
builder=read("tools/build-package.sh")
native=read("tools/build-headless-native.sh")
source=read("headless/main.cpp")
cmake=read("headless/CMakeLists.txt")
release_gate=read("tools/ci/check-release-experiments.py")
jit=read("headless/jit-allocator.h")
boc=read("vendor/encore-active/eden-core/src/dynarmic/backend/x64/block_of_code_native.cpp")
assert "test_all_on:" not in workflow and "EDEN_TEST_ALL_ON" not in workflow
assert "build/dev/PPSA99008" not in workflow
assert 'bash tools/build-package.sh release-stage' in workflow
assert 'bash tools/build-package.sh dev ' not in workflow
assert "Prospero.Eden-Encore-PS5-all-on-test" not in workflow
assert "EDEN_STAGE_DIR: build/release/PPSA99008" in workflow
assert "Eden-Encore-PS5-FTP-PPSA99008" in workflow
assert '\\ndev)\\n' not in builder and "EDEN_SPARSE_JIT_DEV" not in builder
assert "EDEN_SPARSE_JIT_DEV" not in cmake and "EDEN_SPARSE_JIT_DEV" not in native
assert "if(EDEN_FINAL_RELEASE_PROFILE)" in cmake
assert "if(EDEN_SHARED_JIT OR EDEN_JIT_COMPILE_BATCH OR" in cmake
assert "EDEN_SHARED_JIT=OFF EDEN_JIT_COMPILE_BATCH=OFF" in builder
assert "EDEN_EXPERIMENT_DEFAULTS sparse=%u logical_cpu=%u frame_probe=%u safe=%u" in source
assert "experimental_sparse_jit = true;" in source
assert "if (!Common::ProbeSparseJitAlias())" in source
assert 'throw std::runtime_error("PS5 sparse JIT alias preflight failed")' in source
assert "ConfigFile(\"experiments.json\")" not in source
assert "Common::ReserveSparseJitCode(sparse_span, &writable)" in jit
assert "Common::AllocateMemoryPages(size);" not in jit
assert "::Common::CommitSparseJitCode(const_cast<u8*>(getCode()), target.bytes)" in boc
assert "TrimSparseJitCode(const_cast<u8*>(getCode()), begin)" in boc
assert '"EDEN_FINAL_RELEASE_PROFILE:BOOL": "ON"' in release_gate
assert '"EDEN_PS5_VULKAN:BOOL": "ON"' in release_gate
assert '"EDEN_VULKAN_DRIVER:STRING": "RADV"' in release_gate
assert "EDEN_JIT_SPARSE_TRIM released=" in release_gate

# Execute the extracted prebuild shell gates with a fake python3 command, so
# this verifies real Bash flag behavior (not merely the presence of a string).
# Native release must execute the Clang syntax gate, even when prebuild skips the older
# release-only source-contract suite. The explicit prebuild bypass remains valid.
import os
import subprocess
import tempfile

launcher=read("headless/prosperoeden/pe/ui/launcher.cpp")
assert '#include "pe/core/log.hpp"' in launcher
assert 'sys::log("EDEN_UI_HOTSPOT phase=%s elapsed_ms=%lld"' in launcher
assert native.count('check-native-source-syntax.py') == 1
gate_marker="# Native PS5 syntax gate:"
release_marker="# Run every source/harness check"
build_marker='echo "Building Eden with'
assert native.index(gate_marker) < native.index(release_marker) < native.index(build_marker)
gate_shell=native[native.index(gate_marker):native.index(build_marker)]
assert 'check-native-source-syntax.py' in gate_shell.split(release_marker, 1)[0]
assert 'check-native-source-syntax.py' not in gate_shell.split(release_marker, 1)[1]
assert 'check-dummy-thread-waits.py' not in gate_shell  # earlier pinned-source release preflight stays separate

with tempfile.TemporaryDirectory() as tmp:
    calls=Path(tmp)/"calls.txt"
    harness=(
        'set -euo pipefail\n'
        'root=/ci-mock; scratch=/ci-mock; probe=OFF\n'
        'python3() { printf "%s\\n" "$*" >> "$EDEN_GATE_CALLS"; }\n'
        + gate_shell
    )
    def run_gate(skip_source: str, skip_prebuild: str, graphics: str) -> list[str]:
        calls.write_text("")
        env=dict(os.environ, EDEN_GATE_CALLS=str(calls),
                 EDEN_SKIP_SOURCE_CHECKS=skip_source,
                 EDEN_SKIP_PREBUILD_SOURCE_CHECKS=skip_prebuild,
                 graphics=graphics)
        result=subprocess.run(["bash", "-c", harness], env=env, text=True,
                              capture_output=True, timeout=15)
        assert result.returncode == 0, result.stderr
        return calls.read_text().splitlines()

    bypass_source=run_gate("1", "0", "ON")
    assert len(bypass_source)==1 and "check-native-source-syntax.py" in bypass_source[0], bypass_source
    release=run_gate("0", "0", "ON")
    assert release and "check-native-source-syntax.py" in release[0], release
    assert any("check-load-failure.py" in call for call in release), release
    assert run_gate("1", "1", "ON")==[]
    assert run_gate("0", "1", "ON")==[]
    assert run_gate("1", "0", "OFF")==[]
# A real regression check for the argument-vector bug in run #231. The
# upstream-generated units inherit a Clang-18-unsupported -Wno-error-all;
# dropping it in this preflight cannot suppress actual syntax errors.
import runpy
syntax_flags=runpy.run_path(str(root / "tools/check-native-source-syntax.py"))["syntax_check_flags"]
input_flags=["clang++-18", "-std=gnu++20", "-Wno-error-all", "-Wall"]
for generated in (False, True):
    flags=syntax_flags(input_flags, generated=generated)
    assert "-Wno-error-all" not in flags, flags
    assert "-std=gnu++20" in flags and "-Wall" in flags, flags
    assert "-fsyntax-only" in flags and "-ferror-limit=8" in flags, flags
    assert ("-Werror" in flags) == (not generated), flags
assert input_flags == ["clang++-18", "-std=gnu++20", "-Wno-error-all", "-Wall"]
print("PASS: native Clang syntax flags reject invalid upstream alias and preserve compiler error checks")

print("PASS: single native release syntax gate runs with or without source review bypass")

print("PASS SINGLE_PS5_RELEASE_CONTRACT: PS5 sparse JIT on, dev/dense package absent, no shared/batch variant")
print("No PS5 hardware/glyph art qualification, SDK build or CI run")
