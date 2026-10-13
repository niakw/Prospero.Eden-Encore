# CodeQL R419 — security triage for alerts #10–#28

Scope: `dev/ps5-sparse-jit` (October 2026). The GitHub CodeQL *default setup* scans every readable vendored dependency, including upstream generator and test helpers that are neither executed nor shipped as Eden Encore application logic. The original `vendor/sources/` trees and `vendor/objects/` archives are exact SHA-pinned inputs. Do not silently modify original vendor files or release hashes to satisfy scanner findings.

## First-party fixes (5 alerts)
- #23: `tools/ps-glyph-mod-discovery.py` — verify DuckDuckGo DNS-label boundaries before honoring `uddg` redirect metadata; reject lookalike hosts such as `evilduckduckgo.com`. Preserve the separate destination hostname allowlist and strip tracking parameters.
- #22: `tools/check-ps-glyph-curl-search.py` — validate parsed search endpoint schemes, hosts, paths and query fields instead of matching URL text prefixes.
- #19–#21: `tools/check-guest-network-isolation.py` — assert **whole, uncommented denylist entries**, not accidental substrings. Production network DNS filtering is not changed.
- Extend `check-ps-glyph-mod-discovery.py` with lookalike-origin regression examples and run offline tests in CI.

## Vendored source alerts (14 alerts)
- #12–#18: Boost MPL `libs/mpl/preprocessed/pp.py` regexes (upstream formatter).
- #10–#11: Boost Litre `tools/litre/cplusplus.py` temporary-file handling (upstream harness).
- #26–#27: Mesa `bin/nir-test-runner.py` overly broad character class (upstream test runner).
- #24–#25: HarfBuzz `hb_test_tools.py` overly broad character class (upstream test).
- #28: vendored `python/run_tests.py` overly broad character class (upstream test).

These findings are not evidence that the native PS5 emulator executes these tools. They nevertheless remain relevant if a maintainer separately runs upstream scripts with untrusted inputs. The narrow `.github/codeql/codeql-config.yml` exclusions avoid false security confidence from modifying byte-pinned dependencies; all **first-party** tools, `headless`, active renderer forks and runtime code remain eligible for analysis. Do not exclude all of `vendor/`.

**Activation required on GitHub:** This repo currently uses CodeQL *default setup*. Simply adding the config file does not activate it. In repository Settings → Advanced Security → CodeQL setup/repository properties, set the repository property `github-codeql-config-file` to `./.github/codeql/codeql-config.yml`, then allow a new CodeQL analysis on `dev/ps5-sparse-jit` to finish. GitHub introduced this default-setup customization on August 4, 2026. Do not dismiss the 14 alerts as “fixed in code”; classify them as upstream scripts excluded from this application's first-party scope only after CodeQL confirms the exclusion. Reference: https://docs.github.com/en/code-security/concepts/code-scanning/setup-types

Verification gates: syntax compilation, offline domain/canonical-URL unit tests, the existing broad `encore-core-preflight`, and the next scheduled CodeQL scan. Source-level tests are not equivalent to a completed CodeQL run. No new PS5 binary build is necessary for security-only Python and scanning-config changes.
