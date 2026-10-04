# Contributing to Prospero.Eden Encore

Thanks for helping improve Prospero.Eden Encore.

Encore is a focused PS5 homebrew fork of ProsperoEden 1.000.040 whose primary validated target is
**PS5 firmware 13.60**. Changes should preserve that focus unless a separate firmware has been
validated on hardware.

## Before opening an issue or pull request

- Read the [README](README.md), [technical notes](docs/FORK_NOTES.md) and
  [security policy](SECURITY.md).
- Search existing issues and pull requests first.
- Do not include console keys, firmware, copyrighted game data, account data or other private
  material.
- Security vulnerabilities must be reported privately according to [SECURITY.md](SECURITY.md),
  not in a public issue.
- FPKG entitlement/PPR and external kstuff/jailbreak problems are outside Encore's emulator scope
  unless the report demonstrates a separate bug in Encore itself.

## Development principles

Prefer changes that are:

1. **13.60-safe** — do not replace the known working elevation/runtime path without hardware proof.
2. **Small and auditable** — avoid importing a large newer subsystem when a targeted fix is enough.
3. **Recoverable** — preserve user settings/saves and provide an obvious way back from risky
   settings.
4. **Bounded** — caches, logs, allocations and retries should have explicit limits.
5. **Reproducible** — dependencies must be pinned and release inputs verifiable.
6. **Legal to redistribute** — keep third-party attribution and licenses accurate.

## Building

Linux is recommended.

```bash
make toolchain
python3 -B tools/launcher/strings.py check
make release
```

See [docs/BUILDING.md](docs/BUILDING.md) for the complete toolchain.

## Pull requests

A useful pull request should:

- explain the problem and why the change belongs in Encore;
- describe user-visible behavior;
- identify security or compatibility trade-offs;
- include tests or validation when practical;
- keep documentation and translations in sync;
- avoid unrelated refactors;
- pass the release build and CodeQL.

For PS5-specific behavior, state the tested firmware and whether validation was done on real
hardware.

## Third-party code

Do not silently copy third-party code into the repository. Record its source, pinned revision and
license in the appropriate dependency metadata and/or [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Style

Match the surrounding code. Keep changes straightforward and reviewable. Prefer explicit checks over
clever behavior in privileged, filesystem, parser and release code.
