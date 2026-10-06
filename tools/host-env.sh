#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Normalizes the host build environment without changing the Linux CI contract.
eden_host_env() {
    local root=$1
    local base=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    if [[ $(uname -s) == Darwin && -d /opt/homebrew ]]; then
        local llvm=/opt/homebrew/opt/llvm@18/bin
        local shim="$root/.local/llvm18-bin"
        mkdir -p "$shim"
        if [[ -d $llvm ]]; then
            local tool
            for tool in clang clang++ ld.lld ld64.lld llvm-ar llvm-ranlib llvm-nm llvm-objdump llvm-readobj llvm-objcopy llvm-strip; do
                [[ -x "$llvm/$tool" ]] || continue
                ln -sf "$llvm/$tool" "$shim/${tool}-18"
            done
            # Source-check harnesses inherited from the Linux workflow invoke generic GCC/C++
            # names and need the host C++20 library (not the PS5 cross libc++). Current CLT 27
            # TAPI files are newer than the bundled Apple linker on this machine, while SDK 26
            # is fully compatible and exposes std::jthread. Keep this host-only choice isolated.
            local host_sdk=/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk
            if [[ -d $host_sdk ]]; then
                rm -f "$shim/cc" "$shim/gcc" "$shim/c++" "$shim/g++"
                printf '#!/bin/sh\nexec /usr/bin/clang -isysroot %s "$@"\n' "$host_sdk" > "$shim/cc"
                cp "$shim/cc" "$shim/gcc"
                printf '#!/bin/sh\nexec /usr/bin/clang++ -isysroot %s "$@"\n' "$host_sdk" > "$shim/c++"
                cp "$shim/c++" "$shim/g++"
                chmod +x "$shim/cc" "$shim/gcc" "$shim/c++" "$shim/g++"
            fi
        fi
        local py_prefix=
        [[ -x "$root/.local/host-venv/bin/python3" ]] && py_prefix="$root/.local/host-venv/bin:"
        export PATH="${py_prefix}$shim:/opt/homebrew/opt/llvm@18/bin:/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/opt/make/libexec/gnubin:/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:/opt/homebrew/bin:/opt/homebrew/sbin:$base"
    else
        # GitHub Actions installs the release-pinned Meson in ~/.local/bin. Preserve that explicit
        # tool location while still discarding unrelated inherited PATH entries.
        local user_prefix=
        [[ -d "$HOME/.local/bin" ]] && user_prefix="$HOME/.local/bin:"
        export PATH="${user_prefix}$base"
    fi
}

eden_host_jobs() {
    if command -v nproc >/dev/null 2>&1; then
        nproc
    elif command -v sysctl >/dev/null 2>&1; then
        sysctl -n hw.logicalcpu
    elif command -v getconf >/dev/null 2>&1; then
        getconf _NPROCESSORS_ONLN
    else
        echo 4
    fi
}
