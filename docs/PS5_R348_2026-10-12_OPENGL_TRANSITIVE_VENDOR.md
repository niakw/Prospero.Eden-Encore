# R348 — Complete mandatory PS5 OpenGL dependency source chain

Date: 2026-10-12, branch `dev/ps5-sparse-jit`.

## Why this is a separate dependency family

The PS5 OpenGL package is not Mihawk's Mesa RADV fork. The pinned OpenGL SDK (`blackbearreloaded/ps5-opengl` at `ad2807d41cef2681882a9ee0d20808779f74b7cd`) contains its *own* `dependencies.json` and downloads original Mesa **26.2.0**, multiple shader compilers/UI libraries and a distinct PS5 boilerplate. This was not included when we first declared the twelve top-level dependencies vendored. We now pin the original download revisions in our `tools/deps.json`, without changing upstream versions during this source restructuring.

### Mandatory contents

- Seven Git repositories: `opengnm-psbc`, `opengnm`, `SPIRV-Headers`, `Vulkan-Headers`, `imgui`, `nanovg`, `sokol` — full upstream source at each original SHA in `vendor/sources/opengl-*`, original SHA Git object packs in `vendor/objects/opengl-*`.
- Original Mesa **26.2.0**, SHA `efd4bb08cdb7c365a812cd4e6c9202ab55b2f22cdcd13c7d6c4f9647b799a4ef`, in `vendor/sources/opengl-mesa-26-2` plus fully preserved and SHA-indexed original `.tar.xz`. Do **not** replace with `vendor/sources/ps5-mesa`; these are different graphics driver APIs and build recipes.
- The OpenGL SDK's **separate** PS5 native boilerplate at `4f531c4b517f80bcb6b1267135848168d2250047`, including original Git SHA objects; not the same commit as Encore's app boilerplate.
- Both bootstrap byte streams were already vendored: PS5 SDK v0.42 `8cfbc7cd...02da`, and zlib 1.3.2 `bb329a0a...9d16`. They are reconstructed and staged from this repository so upstream does not download them again.

### Native build wiring

`tools/build-opengl-sdk.sh` calls `tools/stage-vendored-opengl-deps.py` **before** checking or fetching the upstream PS5 OpenGL inner repositories. The stager rejects dependency version drift, restores exact Git original commits, copies each into a disposable `third_party/` tree, pre-populates the complete Mesa archive and exact OpenGL native boilerplate, and extracts the SDK with executable Unix file permissions. The original OpenGL fetcher runs afterward and performs its independent PSBC patched-tree and Mesa/Git verification.

### Actual test performed

From a fresh staging root copied from `vendor/sources/opengl-source/`, ran:

```sh
PROSPEROEDEN_DEPS_OFFLINE=1 PROSPEROEDEN_GIT_DEPS_ROOT=/tmp/eden-r348-git-checkouts \
  python3 tools/stage-vendored-opengl-deps.py /tmp/eden-r348-opengl-airgap
GIT_ALLOW_PROTOCOL=file HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 \
  python3 /tmp/eden-r348-opengl-airgap/tools/fetch-sources.py
```

Both exited **zero**; logs confirm all seven Git dependencies verified, `PSBC: exact pinned source tree verified`, `Mesa: archive verified; sources ready for the recorded platform patch`, and bootstrap SDK/zlib preserved. `tools/check-vendored-opengl-deps.py` supplies a fast source pin gate in CI.

## Honest remaining constraints

- The optional upstream test suites `VK-GL-CTS` and `sokol-samples` are NOT part of production OpenGL's fetch closure, and have not been vendored. Their absence should not block native release builds.
- Other transitive dependencies from Eden's CPM or external Meson subproject wraps may still be downloaded on a truly empty build cache. Those are not qualified by this focused OpenGL offline test and need further audit and mirroring before claiming end-to-end zero-network native compilation.
- Vendoring and source equivalence cannot prove FC27's game-specific FPS, textures, DualSense mapping or frozen menu are repaired. Native PS5 CI and ultimately on-console evidence remain separate.
