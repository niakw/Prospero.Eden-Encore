# Eden Encore — unique development branch

The **only active development branch** is `dev/ps5-sparse-jit`, which is also the GitHub default branch. Do not create a `work/*`, `security/*`, `feature/*` or `fix/*` branch for future updates. Make edits directly on the default branch with optimistic SHA checks, audit one change set at a time, and use explicit `[core-ready]` and `[full-build]` gates as needed.

Historical branch clean-up was requested after integrating R428. All R419–R427 changes in the obsolete experiment branches were already represented in the default branch's consolidated commits; R428 was fast-forwarded onto the default branch. Obsolete historical refs are **not** authoritative for the current build. Do not merge them independently and accidentally restore older performance/security experiments.

The remote branch deletion operation requires GitHub branch/ref delete permission and an appropriate API action. The available GitHub connector can read and move references, but has no delete-ref operation; a safe deletion must be carried out through an authorized GitHub UI or another properly authenticated tool. Branch cleanup does not imply deletion of the old commit objects or revert any code.
