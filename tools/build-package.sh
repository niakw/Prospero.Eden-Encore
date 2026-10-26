#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Builds the PS5 app and its PPSA99008 folder (after make prepare).
#   tools/build-package.sh release         build + package + validate the shipping app
#   tools/build-package.sh release-stage   build + package only; validation is a separate resumable CI step
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$root/tools/host-env.sh"
eden_host_env "$root"
cd "$root"
mode=${1:?usage: tools/build-package.sh release|release-stage}
scratch=$(cat .local/headless-cache)
export PS5_PAYLOAD_SDK="$scratch/sdk"
export EDEN_PS5_VULKAN=ON EDEN_VULKAN_DRIVER=RADV
case $mode in
release|release-stage)
    export EDEN_DEV_VULKAN=OFF EDEN_DEV_ROM_ID= EDEN_DEV_PROFILE=OFF EDEN_DEV_WAIT_CALLERS=OFF
    # One shipping native JIT: the sparse allocator is selected by PS5_NATIVE
    # in the engine, not an opt-in flag or alternate packaged mode.
    export EDEN_SHARED_JIT=OFF EDEN_JIT_COMPILE_BATCH=OFF
    export EDEN_FINAL_RELEASE_PROFILE=ON EDEN_DEV_PROFILE_TITLE= EDEN_GPU_PROBE=OFF
    export EDEN_INLINE_EXCLUSIVES=OFF EDEN_DEVICE_FRONTEND=OFF EDEN_HEAP_GUARD=OFF
    export EDEN_GUEST_WRITE_BRIDGE_DEV=OFF EDEN_UNQUALIFIED_FERMI2D_COPY=OFF
    export EDEN_PACKAGE_DIR="$root/build/release/PPSA99008"
    ;;
*)
    echo "usage: tools/build-package.sh release|release-stage" >&2
    exit 2
    ;;
esac
echo "== Eden for the PS5 ($mode, $(git rev-parse --short HEAD 2>/dev/null || echo source)$(git diff --quiet -- headless tools src 2>/dev/null || echo +dirty))"
bash tools/build-headless-native.sh --graphics
python3 -B tools/check-radv-native.py
echo "== Package $EDEN_PACKAGE_DIR"
rm -rf "$EDEN_PACKAGE_DIR"
PS5_ELEVATION_SDK="$root/../ps5-native-app-boilerplate/.deps/native/ps5-payload-sdk" \
    bash tools/package-headless-native.sh --integration
if [[ $mode == release ]]; then
    python3 -B headless/check_package.py --check
elif [[ $mode == release-stage ]]; then
    echo "== Staged $EDEN_PACKAGE_DIR (validation deferred)"
elif [[ -f CANDIDATE.json ]]; then
    # Development layout: the console runner verifies this receipt before every run.
    python3 -B headless/check_package.py --freeze
    python3 -B headless/check_package.py --verify
else
    python3 -B headless/check_package.py --check
fi
echo "== Built $EDEN_PACKAGE_DIR"
