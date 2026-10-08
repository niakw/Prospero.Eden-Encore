#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
template="$root/../ps5-native-app-boilerplate"
sdk="$PS5_PAYLOAD_SDK"
output=$1
shift
libraries=()
radv_archive=""
for argument in "$@"; do
    case "$argument" in
        */libvulkan_radeon.ps5.a) radv_archive="$argument" ;;
        # These functions are supplied by the native libc/kernel providers.
        -Xlinker|-pthread|-lpthread|-ldl|-lrt|-lm) ;;
        # Native titles load libkernel, not the web-process provider. Preserve
        # Eden's qualified sysconf/pthread imports when consuming the GL SDK.
        -lkernel_web) libraries+=("$sdk/target/lib/libkernel.so") ;;
        -Wl,*) IFS=, read -r -a flags <<< "${argument#-Wl,}"; libraries+=("${flags[@]}") ;;
        *) libraries+=("$argument") ;;
    esac
done
radv_link_flags=()
radv_link_inputs=()
tls_flags=(--defsym=__cxa_thread_atexit_impl=0)
if [[ -n $radv_archive ]]; then
    source "$root/tools/radv-link-eden.sh"
    eden_radv_link_recipe "$radv_archive"
    # RADV's platform provides the real thread-local destructor registration.
    tls_flags=()
fi
# The SDK's dlfcn wrappers explicitly return unavailable when these optional
# weak hooks are null. This static frontend supplies no dynamic-loader hooks.
lld="$template/.deps/native/ps5-payload-sdk/bin/prospero-lld"
nm_tool=$(command -v llvm-nm-18 || command -v llvm-nm || command -v nm)

link_native() {
    local target=$1
    local map=$2
    shift 2
    "$lld" \
        "${tls_flags[@]}" "${radv_link_flags[@]}" "$@" -z nodynamic-undefined-weak -L "$sdk/target/lib" \
        --defsym=__dlopen=0 --defsym=__dlsym=0 --defsym=__dladdr=0 \
        --defsym=__dlclose=0 --defsym=__dlerror=0 \
        -T "$template/tooling/native/ps5-pie.ld" -T "$root/tools/unwind.ld" \
        --eh-frame-hdr --gc-sections --version-script "$root/tools/app-symbols.map" -e _start \
        --error-limit=0 -Map="$map" \
        --wrap=aligned_alloc --wrap=malloc --wrap=calloc --wrap=realloc --wrap=free \
        --wrap=posix_memalign --wrap=malloc_usable_size --wrap=fcntl \
        -o "$target" --start-group "${libraries[@]}" "${radv_link_inputs[@]}" \
        "$sdk/target/lib/libc++.a" "$sdk/target/lib/libc++abi.a" "$sdk/target/lib/libunwind.a" \
        --end-group --as-needed "$sdk/target/lib/libSceLibcInternal.so" "$sdk/target/lib/libkernel.so" \
        "$sdk/target/lib/libc.a" "$sdk/target/lib/libSceNet.so"
}

# First pass: let every real static/system provider resolve what it can.
# Mesa dispatch tables intentionally carry weak references for optional hooks; anything weak that
# survives this complete link has no provider on the PS5 and must behave as a NULL function pointer.
weak_scan="$output.weak-scan"
weak_map="$output.weak-scan.map"
link_native "$weak_scan" "$weak_map"
mapfile -t unresolved_weak < <(
    "$nm_tool" -D --undefined-only "$weak_scan" 2>/dev/null |
        awk '$1 ~ /^[wWvV]$/ {print $2}' | sort -u
)

weak_flags=()
for name in "${unresolved_weak[@]}"; do
    [[ $name =~ ^[A-Za-z_][A-Za-z0-9_$.]*$ ]] || {
        echo "Unsafe weak symbol name from linker: $name" >&2
        exit 2
    }
    weak_flags+=("--defsym=${name}=0")
done
printf 'Native weak imports resolved to NULL: %d\n' "${#weak_flags[@]}"
rm -f "$weak_scan" "$weak_map"

# Final link: no unresolved weak symbol is allowed to become a native-title import.
link_native "$output" "$output.map" "${weak_flags[@]}"
if "$nm_tool" -D --undefined-only "$output" 2>/dev/null |
        awk '$1 ~ /^[wWvV]$/ {print $2}' | grep -q .; then
    echo "Native link still contains unresolved weak imports:" >&2
    "$nm_tool" -D --undefined-only "$output" 2>/dev/null |
        awk '$1 ~ /^[wWvV]$/ {print "  " $2}' >&2
    exit 1
fi
