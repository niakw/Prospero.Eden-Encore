#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# GitHub Actions cannot cache relative paths containing "..". Keep the heavy pinned sibling
# checkouts under this repository's cacheable .deps tree and expose their historical sibling names
# through symlinks. Existing real sibling checkouts are never replaced.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
store="${PROSPEROEDEN_GIT_DEPS_ROOT:-.deps/repos}"
[[ "$store" = /* ]] || store="$root/$store"
mkdir -p "$store"

for name in ps5-native-app-boilerplate ps5-opengl-review mihawk-vulkan-review mihawk-mesa-review mihawk-sdk-review; do
    link="$root/../$name"
    target="$store/$name"
    if [[ -e "$link" && ! -L "$link" ]]; then
        echo "Refusing to replace real sibling checkout: $link" >&2
        exit 1
    fi
    rm -f "$link"
    ln -s "$target" "$link"
done

echo "Encore CI sibling cache links: ready under $store"
