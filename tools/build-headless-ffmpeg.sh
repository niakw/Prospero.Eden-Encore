#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$root/tools/host-env.sh"
eden_host_env "$root"
scratch=$(cat "$root/.local/headless-cache")
[[ "$(cd -- "$(cat "$scratch/owner")" && pwd -P)" == "$root" ]]
export PS5_PAYLOAD_SDK="$scratch/sdk"
source="$scratch/source/.cache/cpm/ffmpeg/c7b5f1537d"
test -f "$source/configure"
mkdir -p "$scratch/ffmpeg-native"
cd "$scratch/ffmpeg-native"
# Use the same pinned, minimal decoder set as the Linux core. Avoid the full
# prebuilt FFmpeg package's unrelated codec and C++ runtime dependencies.
bash "$source/configure" --prefix="$scratch/ffmpeg-native/install" \
    --enable-cross-compile --arch=x86_64 --target-os=freebsd \
    --cc="bash $root/tools/ffmpeg-ps5-cc.sh" --ld="bash $root/tools/ffmpeg-ps5-cc.sh" \
    --ar=llvm-ar-18 --ranlib=llvm-ranlib-18 --nm=llvm-nm-18 --strip=llvm-strip-18 \
    --disable-autodetect --disable-everything --disable-programs --disable-doc \
    --disable-avdevice --disable-avformat --disable-network --disable-swresample \
    --enable-decoder=h264,vp8,vp9 --enable-filter=yadif,scale --enable-pic \
    --enable-pthreads --disable-shared --enable-static
make -j"${EDEN_BUILD_JOBS:-$(eden_host_jobs)}"
make install
