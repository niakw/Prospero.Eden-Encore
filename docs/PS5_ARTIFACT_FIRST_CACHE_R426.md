# R426 — PS5 artifact-first native build hardening

R422 reached `Save build caches immediately after staging` only after the expensive native PS5 compilation. That step can run for a long time because it uploads toolchain/CMake/dependency caches while the **usable PS5 ZIP and crash symbols have not yet been uploaded**. A cancelled/failed optional cache upload therefore discards an otherwise completed console build.

R426 adjusts only `.github/workflows/build-040-zbic.yml`:

1. Keep build, package metadata checks, all-on ZIP root validation, actual uploaded ZIP extraction verification, and crash symbol upload.
2. Keep the release staged app and compiled release bundle uploads.
3. **After** those essential artifacts have been uploaded, save incremental caches as a last optional step.
4. Add `continue-on-error: true` for cache persistence. A cache service outage cannot invalidate a successful PS5 image or release. Caches continue to use the previous immutable run-scoped hash key and the same file paths.

The source-only `tools/check-ci-cache.py` now enforces ordering and cache failure isolation. This does not affect PS5 runtime, shaders, actual frame duration, native compiler command lines, or the vendored hashes. It reduces lost builds and repeated physical-test delays.

R426 is intentionally staged **outside** `dev/ps5-sparse-jit` while R422 is still running to avoid another cancellation of the active native job.
