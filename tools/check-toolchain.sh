#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Reports the host tools the build uses (make toolchain). See docs/BUILDING.md.
set -uo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$root/tools/host-env.sh"
eden_host_env "$root"
missing=0
need() {
    local label=$1; shift
    for command in "$@"; do
        if command -v "$command" >/dev/null 2>&1; then
            printf '  %-28s %s\n' "$label" "$(command -v "$command")"
            return
        fi
    done
    printf '  %-28s MISSING (%s)\n' "$label" "$*"
    missing=$((missing + 1))
}
echo "Compilers and LLVM 18:"
for tool in clang-18 clang++-18 ld.lld-18 llvm-ar-18 llvm-ranlib-18 llvm-nm-18 llvm-readobj-18 llvm-strip-18; do need "$tool" "$tool"; done
echo "Build tools:"
for tool in cmake ninja ccache make nasm meson rsync git flock ar pkg-config autoconf; do need "$tool" "$tool"; done
for tool in realpath install xargs sort head; do need "$tool" "$tool"; done
need glslangValidator glslangValidator
need spirv-val spirv-val
need "bison / flex" bison
need flex flex
echo "Downloads and archives:"
for tool in curl wget unzip tar sha256sum; do need "$tool" "$tool"; done
echo "Python:"
if python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    printf '  %-28s %s\n' "python3 >= 3.12" "$(python3 --version)"
else
    printf '  %-28s MISSING\n' "python3 >= 3.12"; missing=$((missing + 1))
fi
for module in venv mako yaml packaging; do
    if python3 -c "import $module" 2>/dev/null; then
        printf '  %-28s ok\n' "python3 module $module"
    else
        printf '  %-28s MISSING\n' "python3 module $module"; missing=$((missing + 1))
    fi
done
if (( missing )); then
    echo "$missing tool(s) missing (Ubuntu 24.04: see docs/BUILDING.md)."
    exit 1
fi
echo "All host tools found."
