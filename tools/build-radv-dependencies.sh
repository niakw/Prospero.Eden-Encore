#!/usr/bin/env bash
# Build isolated, pinned RADV dependencies; never deploy or replace the old SDK.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$root/tools/host-env.sh"
eden_host_env "$root"
refs=$(dirname "$root")
export PS5_MESA_FORK="$refs/mihawk-mesa-review"
export PS5_PAYLOAD_SDK_FORK="$refs/mihawk-sdk-review"
vulkan="$refs/mihawk-vulkan-review"
pin() {
    python3 - "$root/tools/deps.json" "$1" <<'PY'
import json, sys
manifest, name = sys.argv[1], sys.argv[2]
data = json.load(open(manifest))
print(next(item["commit"] for item in data["items"] if item["name"] == name))
PY
}
for check in "ps5-vulkan-tools $vulkan" "ps5-mesa $PS5_MESA_FORK" "ps5-payload-sdk-fork $PS5_PAYLOAD_SDK_FORK"; do
    read -r name path <<< "$check"
    actual=$(git -C "$path" rev-parse HEAD)
    expected=$(pin "$name")
    [[ $actual == "$expected" ]] || {
        echo "$path is at $actual, expected $expected from tools/deps.json" >&2
        exit 1
    }
done
if [[ $(uname -s) == Darwin ]]; then
    jobs=${EDEN_BUILD_JOBS:-$(eden_host_jobs)}
else
    jobs=${EDEN_BUILD_JOBS:-24}
fi
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo "Invalid EDEN_BUILD_JOBS: $jobs" >&2; exit 1; }
export BUILD_JOBS="$jobs" CMAKE_BUILD_PARALLEL_LEVEL="$jobs"
mkdir -p "$root/build/radv-tools"
# Upstream calls ninja directly; enforce the same bounded parallelism everywhere.
ninja_bin=$(command -v ninja)
printf '#!/bin/sh\nexec %s -j%s "$@"\n' "$ninja_bin" "$jobs" > "$root/build/radv-tools/ninja"
chmod +x "$root/build/radv-tools/ninja"
export NINJA="$root/build/radv-tools/ninja"
command -v ccache >/dev/null
# Cross compilers do not get Meson's automatic native ccache detection. Derive the two-line ccache
# adaptation temporarily, and always restore the pinned upstream file on exit so dependency repos
# remain clean and `git status` continues to mean something.
cross_ini="$vulkan/tooling/radv/ps5-cross.ini"
cross_base="$root/build/radv-tools/ps5-cross.ini.upstream"
git -C "$vulkan" show HEAD:tooling/radv/ps5-cross.ini > "$cross_base"
python3 - "$cross_ini" "$cross_base" <<'PY'
from pathlib import Path
import sys
current, base = map(Path, sys.argv[1:])
original = base.read_text()
derived = original
for lang, compiler in [('c', 'prospero-clang'), ('cpp', 'prospero-clang++')]:
    plain = f"{lang} = sdk / 'bin/{compiler}'"
    cached = f"{lang} = ['ccache', sdk / 'bin/{compiler}']"
    assert plain in derived, 'Unexpected pinned upstream cross compiler configuration'
    derived = derived.replace(plain, cached)
now = current.read_text()
assert now in (original, derived), 'Unexpected local changes in PS5_Vulkan ps5-cross.ini'
current.write_text(derived)
PY
restore_cross_ini() { cp "$cross_base" "$cross_ini"; }
trap restore_cross_ini EXIT
if [[ $(uname -s) == Darwin ]]; then
    # zlib configures Apple's `libtool -o` archive convention on Darwin, while
    # this pinned bootstrap intentionally substitutes llvm-ar. Give make the
    # matching llvm-ar operation without editing the pinned dependency tree.
    MAKEFLAGS=-e ARFLAGS=rcs bash "$vulkan/tools/setup-native-dependencies.sh"
    # Apple's current CLT linker cannot consume the SDK 27 TAPI arm64e.x1
    # descriptors on this host. Mesa's native generator tools use the tested
    # Homebrew LLVM 18 pair; the PS5 cross compiler remains defined by Meson.
    export CC=clang-18 CXX=clang++-18
    bash "$root/tools/prepare-macos-llvm-spirv.sh"
    spirv_prefix="$root/.local/spirv-llvm-translator-18"
    export PKG_CONFIG_PATH="$spirv_prefix/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    export CMAKE_PREFIX_PATH="$spirv_prefix${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
else
    bash "$vulkan/tools/setup-native-dependencies.sh"
fi
# Meson may leave a partial directory after a failed host configure. A later
# setup cannot reliably reuse it unless build.ninja was written.
for partial in "$vulkan/.deps/work/radv-clc-build" "$vulkan/.deps/work/radv-build-ps5-release"; do
    [[ ! -d $partial || -f $partial/build.ninja ]] || rm -rf "$partial"
done
bash "$vulkan/tools/build-radv.sh" release
python3 "$root/tools/patch-radv-wsi.py"
bash "$vulkan/tools/build-radv.sh" release
sha256sum "$vulkan/.deps/work/radv-src/src/vulkan/wsi/wsi_common_videoout.c" \
    > "$vulkan/.deps/native/radv-release/EDEN_WSI_SHA256"
