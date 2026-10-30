# Eden Encore — Git history compaction (2026-10-30)

## Result and boundaries

The active Encore parent Git history was rewritten on 2026-10-30 after `vendor/` was externalized to `niakw/Prospero.Eden-Encore-vendor`. The original Git objects remain safely archived in the external vendor repository release. No PS5 release build was requested by this operation.

- Original parent branch tip before force-with-lease cutover: `fc603828002ad5df0c2177065624229266b874d5`.
- Rewritten parent branch tip at cutover: `a0105af28d235f47217122df4dc7db1e88775421` (later verification commits may advance HEAD).
- Original vendor submodule gitlink: `8c354e6714558c3c88f7ca98d23551168cb680ea` (unchanged on the engine branch).
- Recovery release: https://github.com/niakw/Prospero.Eden-Encore-vendor/releases/tag/encore-original-history-20261030
- Original complete Git bundle asset: `encore-pre-rewrite-all-refs.bundle`, size 1,250,060,087 bytes, SHA-256 `c0a653a8f16ad5af85e05529d8fb7f347b7c62d9fa1ed03ffce6aca35a409357`.
- Read-only history-rewrite audit: https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40993767409 (1.16 GiB mirror before; 99.43 MiB filtered mirror).
- Actual full branches-and-tags clone verification: https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40995353680 (`105296 KiB` of Git metadata; `git fsck` and the original `vendor` gitlink passed).

All then-current heads and six tags were rewritten atomically, with the four active development branches preserved. Exact vendor trees for Avatar, feature lab, and NS2 research are archived in the vendor repository branches:

- `archive/encore-avatar-20261030` — `0abe15411a914c62905535567645ec04c2d5384b`
- `archive/encore-feature-20261030` — `c62ecbb58555fd71b13f98266e745fe22789111d`
- `archive/encore-ns2-20261030` — `be590fba64eca04cf134f5aa322f747bf5eba536`

The original open Avatar PR #19 was closed by GitHub when its history became incompatible with the rewritten base. The same six source blobs were rebased without changing `vendor` in replacement PR #21: https://github.com/niakw/Prospero.Eden-Encore/pull/21 . Review and console verification remain separate; PR #21 was not automatically merged.

## Important: old local Git clones

**Do not merge or push old ancestor histories from a pre-rewrite clone.** Doing so could bring large removed vendor objects back into reachable branch history.

Recommended: make a fresh clone into a **new directory**, preserving the old local checkout as a backup until all local uncommitted changes are accounted for.

```bash
git clone --single-branch --branch dev/ps5-sparse-jit https://github.com/niakw/Prospero.Eden-Encore.git Encore-clean
# Only when preparing a build or the source audits:
git -C Encore-clean submodule update --init --recursive vendor
```

Parent Git storage and submodule disk use are different measurements: checking out the complete vendor repository will still download its large source and archive snapshots. The historical audit size is for the parent Git object database, **without checking out vendor**.

To recover the original history from the permanent bundle, download it from the release and verify the recorded SHA-256 before using `git bundle verify`. Do **not** merge the original bundle commits into the active compact repository.

## Server-side size limitation

GitHub's repository metadata may continue to report the old storage size because internal `refs/pull/*` references and cached unreachable objects can retain history even after all writable branches and tags have been rewritten. Ordinary clone size is independently verified as small. It is **not proven** that GitHub server-side storage has fallen below 1 GiB.

For a strict new GitHub repository storage-size target that excludes old pull-request references, a **new clean GitHub repository** populated from the rewritten heads/tags is the reliable isolation path; migrating/renaming the repository requires explicit account-level actions. Do not delete old PRs or rewrite additional refs just to chase the display number without verifying recoverability.

## Operational guardrails

- Continue F07 on `dev/ps5-sparse-jit` at its current HEAD, not at historical SHAs.
- Any `vendor/encore-active` edit must be committed to the vendor repository first, then reflected in Encore by a new pinned gitlink commit.
- Keep source builds gated; this history cleanup is not a PS5 performance or FC27 proof.
- Preserve the recovery release while any historical baseline, tag, or PR discussion may still be needed.
