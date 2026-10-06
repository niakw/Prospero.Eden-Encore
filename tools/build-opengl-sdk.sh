#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build Encore's frozen PS5 OpenGL SDK from the audited upstream source snapshot.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$root/tools/host-env.sh"
eden_host_env "$root"
source_dir="$root/../ps5-opengl-review"
expected=ad2807d41cef2681882a9ee0d20808779f74b7cd
prefix="$root/.local/ps5-opengl-sdk-ad2807d"
marker="$prefix/ENCORE_SOURCE_COMMIT"
[[ -d $source_dir/.git ]] || { echo "Missing pinned PS5 OpenGL source: run make deps" >&2; exit 1; }
# PS5 OpenGL records its own boilerplate/PayloadSDK pair. Do not combine its source snapshot with
# Encore's older application-template pin: build the graphics SDK against the exact upstream pair.
read -r template_url template_revision < <(python3 - "$source_dir/dependencies.json" <<'PY2'
import json, sys
pin = json.load(open(sys.argv[1]))["native_boilerplate"]
print(pin["url"], pin["revision"])
PY2
)
template="$source_dir/build/native-app-boilerplate"
sdk="$template/.deps/native/ps5-payload-sdk"

actual=$(git -C "$source_dir" rev-parse HEAD)
[[ $actual == "$expected" ]] || { echo "PS5 OpenGL pin mismatch: $actual != $expected" >&2; exit 1; }
git -C "$source_dir" diff --quiet -- && git -C "$source_dir" diff --cached --quiet -- || {
    echo "PS5 OpenGL tracked source is modified" >&2; exit 1;
}

if [[ ! -d $template/.git ]]; then
    rm -rf "$template"
    git clone --quiet "$template_url" "$template"
fi
if [[ $(git -C "$template" rev-parse HEAD) != "$template_revision" ]]; then
    git -C "$template" fetch --quiet origin "$template_revision" || true
    git -C "$template" -c advice.detachedHead=false checkout --quiet --detach "$template_revision"
fi
[[ $(git -C "$template" rev-parse HEAD) == "$template_revision" ]] || {
    echo "PS5 OpenGL boilerplate pin mismatch" >&2; exit 1;
}
git -C "$template" diff --quiet -- && git -C "$template" diff --cached --quiet -- || {
    echo "PS5 OpenGL boilerplate source is modified" >&2; exit 1;
}
if [[ ! -x $sdk/bin/prospero-clang ]]; then
    if [[ $(uname -s) == Darwin ]]; then
        (cd "$template" && MAKEFLAGS=-e ARFLAGS=rcs bash tools/setup-native-dependencies.sh)
    else
        (cd "$template" && bash tools/setup-native-dependencies.sh)
    fi
fi
[[ -x $sdk/bin/prospero-clang ]] || { echo "PS5 OpenGL PayloadSDK setup failed" >&2; exit 1; }

valid=0
if [[ -f $marker && -f $prefix/manifest.sha256 && -s $prefix/lib/libps5_opengl_core33.a ]] &&
   [[ $(cat "$marker") == "$expected" ]]; then
    if (cd "$prefix" && sha256sum --check --strict manifest.sha256 >/dev/null 2>&1); then
        valid=1
    fi
fi
if [[ $valid == 1 ]]; then
    echo "PS5 OpenGL SDK ${expected:0:7}: cached and verified"
    exit 0
fi

stage="$root/.local/.ps5-opengl-sdk-ad2807d.stage.$$"
rm -rf "$stage"
mkdir -p "$root/.local"

# PayloadSDK currently describes the PS5 as target_machine only. Mesa 26.2 selects architecture-
# specific sources from Meson's host_machine, so an Apple-Silicon build host would otherwise make
# the x86_64 PS5 cross-build try to compile AArch64/NEON sources. Add the equivalent host_machine
# section only for this build, then restore the SDK file byte-for-byte on exit.
cross_file="$sdk/toolchain/prospero.ini"
cross_backup=""
if ! grep -q '^\[host_machine\]' "$cross_file"; then
    cross_backup="${cross_file}.encore-backup.$$"
    cp "$cross_file" "$cross_backup"
    cat >> "$cross_file" <<'EOF_CROSS'

[host_machine]
system = 'freebsd'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
EOF_CROSS
    # A Meson build directory records machine identity. Keep an already-correct x86_64 PS5 cache
    # across retries, but discard any directory that was configured as the Apple-Silicon host.
    mesa_build="$source_dir/build/mesa-ps5-probe"
    mesa_log="$mesa_build/meson-logs/meson-log.txt"
    if [[ ! -f $mesa_build/build.ninja ]] ||
       ! grep -q 'Host machine cpu family: x86_64' "$mesa_log" 2>/dev/null ||
       grep -q 'blake3_neon' "$mesa_build/build.ninja" 2>/dev/null; then
        rm -rf "$mesa_build" "$source_dir/build/mesa-ps5-ccache.ini"
    else
        echo 'Mesa PS5 x86_64 cache: verified and reusable'
    fi
fi
host_test="$source_dir/tests/ps5/test_compute_bindings.py"
host_test_backup=""
cleanup() {
    if [[ -n ${host_test_backup:-} && -f $host_test_backup ]]; then
        mv -f "$host_test_backup" "$host_test"
    fi
    if [[ -n ${cross_backup:-} && -f $cross_backup ]]; then
        mv -f "$cross_backup" "$cross_file"
    fi
    rm -rf -- "$stage"
}
trap cleanup EXIT

# Upstream's own fetcher pins and hashes Mesa/compiler dependencies. Building the SDK here keeps
# Encore on a reviewed source commit instead of silently consuming an untagged moving HEAD.
python3 "$source_dir/tools/fetch-sources.py"

# Mesa's vendored c99_alloca.h relies on stdlib exposing alloca. Modern Apple SDKs do not do that
# for this GNU-C host build, while Clang provides the exact builtin Mesa expects. Scope the alias to
# the host PSBC/Mesa build only; the pinned source tree and the PS5 cross compiler remain untouched.
opengl_host_path=$PATH
if [[ $(uname -s) == Darwin ]]; then
    host_bin="$root/.local/opengl-host-bin"
    mkdir -p "$host_bin"
    host_gcc=/opt/homebrew/opt/llvm@18/bin/clang
    host_gxx=/opt/homebrew/opt/llvm@18/bin/clang++
    # PSBC links BLAKE3's portable implementation only. Disable the ARM NEON dispatch path for
    # these host tools or Apple Silicon would reference blake3_hash_many_neon without linking it.
    host_include="$root/.local/opengl-host-include"
    mkdir -p "$host_include"
    printf '#include <sys/endian.h>\n' > "$host_include/endian.h"
    printf '#!/bin/sh\nexec %q -I%q -D_DARWIN_C_SOURCE=1 -Dalloca=__builtin_alloca -DBLAKE3_USE_NEON=0 -include strings.h "$@"\n' "$host_gcc" "$host_include" > "$host_bin/gcc"
    printf '#!/bin/sh\nexec %q -I%q -D_DARWIN_C_SOURCE=1 -Dalloca=__builtin_alloca -DBLAKE3_USE_NEON=0 -include strings.h "$@"\n' "$host_gxx" "$host_include" > "$host_bin/g++"
    cp "$host_bin/gcc" "$host_bin/cc"
    cp "$host_bin/g++" "$host_bin/c++"
    # Upstream's shader-cache test intentionally creates a GNU thin archive. Apple ar silently
    # creates/handles a different archive shape, and Apple ranlib rejects its synthetic member.
    # Keep creation and inspection on LLVM's thin-archive implementation for the host test.
    printf '#!/bin/sh\nexec /opt/homebrew/opt/llvm@18/bin/llvm-ar "$@"\n' > "$host_bin/ar"
    printf '#!/bin/sh\nexec /opt/homebrew/opt/llvm@18/bin/llvm-ranlib "$@"\n' > "$host_bin/ranlib"
    # Some upstream host-only harnesses link extracted PS5 driver functions which retain weak
    # sceKernelDebugOutText references. Let macOS resolve those dynamically instead of injecting
    # an extra object into the executable: the extra object can perturb the harness's 64 KiB BSS
    # alignment, while the weak diagnostic symbol is never required on the host.
    cat > "$host_bin/clang-18" <<EOF_CLANG
#!/bin/sh
compile_only=0
for arg in "\$@"; do
    case "\$arg" in -c|-E|-S) compile_only=1 ;; esac
done
if [ "\$compile_only" -eq 1 ]; then
    exec /opt/homebrew/opt/llvm@18/bin/clang -I'$host_include' -D_DARWIN_C_SOURCE=1 -Dalloca=__builtin_alloca -DBLAKE3_USE_NEON=0 -include strings.h "\$@"
fi
exec /opt/homebrew/opt/llvm@18/bin/clang -I'$host_include' -D_DARWIN_C_SOURCE=1 -Dalloca=__builtin_alloca -DBLAKE3_USE_NEON=0 -include strings.h "\$@" -Wl,-undefined,dynamic_lookup
EOF_CLANG
    chmod +x "$host_bin/gcc" "$host_bin/g++" "$host_bin/cc" "$host_bin/c++" "$host_bin/ar" "$host_bin/ranlib" "$host_bin/clang-18"
    opengl_host_path="$host_bin:$PATH"
fi

# ld64 caps static BSS alignment below the 64 KiB alignment exercised by the upstream MSAA/image
# harness. That makes the host test nondeterministic even though PS5 allocations are 64 KiB-aligned.
# Over-allocate and align the three host-test buffers manually, then restore the pinned test file.
if [[ $(uname -s) == Darwin ]]; then
    host_test_backup="${host_test}.encore-backup.$$"
    cp "$host_test" "$host_test_backup"
    python3 - "$host_test" <<'PYTEST'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
replacements = [
    ("    _Alignas(65536) static uint8_t msaa_pixels[131072];\n",
     "    static uint8_t msaa_storage[131072 + 65535];\n"
     "    uint8_t *msaa_pixels=(uint8_t *)(((uintptr_t)msaa_storage + 65535u) & ~(uintptr_t)65535u);\n"),
    ("    _Alignas(65536) static uint8_t canonical_pixels[131072];\n",
     "    static uint8_t canonical_storage[131072 + 65535];\n"
     "    uint8_t *canonical_pixels=(uint8_t *)(((uintptr_t)canonical_storage + 65535u) & ~(uintptr_t)65535u);\n"),
    ("    static _Alignas(65536) uint8_t tiled_pixels[262144];\n",
     "    static uint8_t tiled_storage[262144 + 65535];\n"
     "    uint8_t *tiled_pixels=(uint8_t *)(((uintptr_t)tiled_storage + 65535u) & ~(uintptr_t)65535u);\n"),
]
for old, new in replacements:
    assert old in s, old
    s = s.replace(old, new, 1)
s = s.replace("msaa.allocation_size=sizeof(msaa_pixels);", "msaa.allocation_size=131072u;", 1)
s = s.replace("canonical.data=canonical_pixels; canonical.allocation_size=sizeof(canonical_pixels);",
              "canonical.data=canonical_pixels; canonical.allocation_size=131072u;", 1)
s = s.replace("memset(canonical_pixels,0x79,sizeof(canonical_pixels));",
              "memset(canonical_pixels,0x79,131072u);", 1)
s = s.replace("for(unsigned i=0;i<sizeof(canonical_pixels);++i)",
              "for(unsigned i=0;i<131072u;++i)", 1)
s = s.replace("assert(ps5_tiled_color_surface_size(tiled.base.format,129,129)==sizeof(tiled_pixels));",
              "assert(ps5_tiled_color_surface_size(tiled.base.format,129,129)==262144u);", 1)
p.write_text(s)
PYTEST
fi
PATH="$opengl_host_path" make -C "$source_dir" sdk-gl46 \
    PS5_PAYLOAD_SDK="$sdk" \
    PS5_OPENGL_SDK_PREFIX="$stage"
if [[ -n ${host_test_backup:-} && -f $host_test_backup ]]; then
    mv -f "$host_test_backup" "$host_test"
    host_test_backup=""
fi
(cd "$stage" && sha256sum --check --strict manifest.sha256 >/dev/null)
printf '%s\n' "$expected" > "$stage/ENCORE_SOURCE_COMMIT"
printf '%s\n' 'Includes upstream 1.0.1 plus 217da45 constant-buffer/alignment and 67c873f scanout flush.' \
    > "$stage/ENCORE_AUDIT_FIXES"
rm -rf "$prefix"
mv "$stage" "$prefix"
if [[ -n ${cross_backup:-} && -f $cross_backup ]]; then
    mv -f "$cross_backup" "$cross_file"
fi
trap - EXIT
echo "PS5 OpenGL SDK ${expected:0:7}: built and verified"
