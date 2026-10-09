#!/usr/bin/env python3
"""Read-only pre-build proof that the all-on PS5 dev workflow cannot silently
become a standard dense/release build. No compilation or PS5 test here.
"""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
read=lambda name:(root/name).read_text("utf-8")
workflow=read(".github/workflows/build-040-zbic.yml")
builder=read("tools/build-package.sh")
native=read("tools/build-headless-native.sh")
source=read("headless/main.cpp")
cmake=read("headless/CMakeLists.txt")
binary_gate=read("tools/ci/check-all-on-test-binary.py")

assert "test_all_on:" in workflow
assert "test_title_id:" in workflow
assert "test \"$GITHUB_REF\" = refs/heads/dev/ps5-sparse-jit" in workflow
assert 'test "${{ inputs.publish }}" != true' in workflow
assert 'bash tools/build-package.sh dev "$EDEN_TEST_TITLE_ID"' in workflow
assert "EDEN_TEST_ALL_ON: ${{ (inputs.test_all_on || (github.ref == 'refs/heads/dev/ps5-sparse-jit' && contains(github.event.head_commit.message || '', '[test-all-on]'))) && '1' || '0' }}" in workflow
assert "EDEN_STAGE_DIR: ${{ (inputs.test_all_on || (github.ref == 'refs/heads/dev/ps5-sparse-jit' && contains(github.event.head_commit.message || '', '[test-all-on]'))) && 'build/dev/PPSA99008' || 'build/release/PPSA99008' }}" in workflow
assert "if: ${{ env.EDEN_TEST_ALL_ON != '1' }}" in workflow
assert "if: ${{ success() && env.EDEN_TEST_ALL_ON != '1' }}" in workflow
assert "!inputs.test_all_on &&" in workflow
assert 'Prospero.Eden-Encore-PS5-all-on-test' in workflow
assert 'python3 -B tools/ci/check-all-on-test-binary.py "$EDEN_STAGE_DIR" "$EDEN_TEST_TITLE_ID"' in workflow
assert 'export EDEN_SPARSE_JIT_DEV=ON' in builder
assert 'export EDEN_SHARED_JIT=OFF EDEN_JIT_COMPILE_BATCH=OFF EDEN_SPARSE_JIT_DEV=OFF' in builder
assert '-DEDEN_SPARSE_JIT_DEV="${EDEN_SPARSE_JIT_DEV:-OFF}"' in native
assert 'option(EDEN_SPARSE_JIT_DEV "Allow developer-only PS5 sparse JIT cache experiments" OFF)' in cmake
assert 'target_compile_definitions(eden-headless PRIVATE EDEN_SPARSE_JIT_DEV=1)' in cmake
assert 'experimental_sparse_jit = true;' in source
assert 'experimental_logical_cpu = true;' in source
assert 'experimental_frame_probe = true;' in source
assert 'if (experimental_sparse_jit && !Common::ProbeSparseJitAlias())' in source
assert 'ConfigFile("experiments.json")' not in source
assert 'if (!safe_launch)' in source
assert 'experimental_sparse_jit = false;' in source  # alias probe
assert '"EDEN_SPARSE_JIT_DEV:BOOL": "ON"' in binary_gate
assert '"EDEN_DEV_PROFILE:BOOL": "ON"' in binary_gate
assert '"EDEN_PS5_VULKAN:BOOL": "ON"' in binary_gate
assert '"EDEN_VULKAN_DRIVER:STRING": "RADV"' in binary_gate
assert "native_ps5_execution_verified" in binary_gate

# Execute the extracted prebuild shell gates with a fake python3 command, so
# this verifies real Bash flag behavior (not merely the presence of a string).
# Dev all-on must execute native Clang syntax even though it skips the older
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

    dev=run_gate("1", "0", "ON")
    assert len(dev)==1 and "check-native-source-syntax.py" in dev[0], dev
    release=run_gate("0", "0", "ON")
    assert release and "check-native-source-syntax.py" in release[0], release
    assert any("check-load-failure.py" in call for call in release), release
    assert run_gate("1", "1", "ON")==[]
    assert run_gate("0", "1", "ON")==[]
    assert run_gate("1", "0", "OFF")==[]
print("PASS: PS5 native syntax gate runs in dev/release, honors prebuild bypass, keeps release-only checks isolated")

print("PASS ALL_ON_PS5_TEST_CONTRACT: compiled dev profile with sparse + RADV + diagnostics; shipping remains OFF")
print("No PS5 hardware/glyph art qualification, SDK build or CI run")
