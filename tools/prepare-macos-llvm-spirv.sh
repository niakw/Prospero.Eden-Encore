#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the LLVM 18 SPIR-V translator required by Mesa's native mesa_clc on macOS.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ $(uname -s) == Darwin ]] || exit 0
source "$root/tools/host-env.sh"
eden_host_env "$root"
repo=https://github.com/KhronosGroup/SPIRV-LLVM-Translator.git
revision=cd8fd419bc50cd2b60bf514eb61d015a10318446 # v18.1.8
src="$root/.local/spirv-llvm-translator-18-src"
build="$root/.local/spirv-llvm-translator-18-build"
install="$root/.local/spirv-llvm-translator-18"
pc="$install/lib/pkgconfig/LLVMSPIRVLib.pc"
if [[ -f $pc ]]; then
    exit 0
fi
if [[ ! -d $src/.git ]]; then
    rm -rf "$src"
    git init -q "$src"
    git -C "$src" remote add origin "$repo"
fi
if ! git -C "$src" cat-file -e "$revision^{commit}" 2>/dev/null; then
    git -C "$src" fetch -q --depth=1 origin "$revision"
fi
if [[ $(git -C "$src" rev-parse HEAD 2>/dev/null || true) != "$revision" ]]; then
    git -C "$src" -c advice.detachedHead=false checkout -q --detach "$revision"
fi
cmake -S "$src" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$install" \
    -DCMAKE_C_COMPILER=clang-18 \
    -DCMAKE_CXX_COMPILER=clang++-18 \
    -DLLVM_DIR=/opt/homebrew/opt/llvm@18/lib/cmake/llvm \
    -DLLVM_SPIRV_INCLUDE_TESTS=OFF \
    -DCCACHE_ALLOWED=ON
cmake --build "$build" -j"$(eden_host_jobs)"
cmake --install "$build"
[[ -f $pc ]] || { echo "LLVMSPIRVLib.pc was not installed" >&2; exit 1; }
