# Eden Encore — pinned vendor submodule

The directory `vendor/` remains at the same relative path as before, but is a pinned Git submodule of `niakw/Prospero.Eden-Encore-vendor`.

## Clone and checkout

```bash
git clone --recurse-submodules https://github.com/niakw/Prospero.Eden-Encore.git
# Or, in an existing working copy:
git submodule sync --recursive
git submodule update --init --recursive vendor
git submodule status vendor
```

All build and validation workflows initialize the pinned submodule. When the gitlink changes, parent-repository Git diffs report **`vendor`**, not `vendor/encore-active/**`; workflow path filters must therefore include `vendor` and `.gitmodules`.

## Update procedure

The submodule is locked to an immutable commit. Commit vendor changes in `niakw/Prospero.Eden-Encore-vendor`, then commit the updated `vendor` gitlink in Encore and rerun preflight/build checks. Active F07 edits under `vendor/encore-active/**` now require a coordinated vendor commit and parent gitlink bump. Keep the exact dependency licenses and source hashes.

## Storage limitation

This reduces the current parent working-tree content but **does not remove old vendor blobs from the parent repository's Git history**. A decrease in GitHub's reported repository storage or full-history clone size needs separate history cleanup, which must not be performed during ongoing F07 optimizations. Prefer shallow/partial clones where suitable.

The initial vendor repository import is required to pass an exact Git tree hash comparison before the parent gitlink is activated. A successful checkout and build/preflight checks are required before merging this branch.
