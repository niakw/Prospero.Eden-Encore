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
assert "EDEN_TEST_ALL_ON: ${{ inputs.test_all_on && '1' || '0' }}" in workflow
assert "EDEN_STAGE_DIR: ${{ inputs.test_all_on && 'build/dev/PPSA99008' || 'build/release/PPSA99008' }}" in workflow
assert "if: ${{ !inputs.test_all_on }}" in workflow
assert "if: ${{ success() && !inputs.test_all_on }}" in workflow
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
print("PASS ALL_ON_PS5_TEST_CONTRACT: compiled dev profile with sparse + RADV + diagnostics; shipping remains OFF")
print("No PS5 hardware/glyph art qualification, SDK build or CI run")
