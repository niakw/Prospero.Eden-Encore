# Support

## Supported target

Prospero.Eden Encore currently treats **PS5 firmware 13.60** as its tested release target.

Other firmware versions may work through underlying PS5 tooling, but they are not claimed as
validated by Encore until tested on hardware.

## Before asking for help

Please check:

1. [README.md](README.md) for installation, compatibility and recommended defaults.
2. [docs/FORK_NOTES.md](docs/FORK_NOTES.md) for technical limitations and validation history.
3. The launcher's **Diagnostics** screen for filesystem mode, free space, cache and logs.
4. **Safe Launch** if one title no longer starts after changing settings.
5. [INSTALL.md](INSTALL.md) if the PS5/Encore language is French but the launcher still appears in English; a complete install must include all 29 `ui/lang/*.po` catalogs.

Useful reports include the Encore version/commit, PS5 firmware, renderer, relevant settings, exact
steps, and sanitized logs.

## What this project can help with

- Encore build or packaging failures;
- launcher/runtime crashes;
- regressions introduced by Encore;
- ZBIC/NSO loader behavior;
- renderer, controller, save-transfer or settings bugs in Encore;
- reproducible performance or compatibility regressions;
- documentation and translation problems.

## Out of scope

This repository does not provide:

- console keys or firmware;
- game downloads or copyrighted content;
- help finding ROM/NSP/XCI sources;
- PS5 FPKG entitlement/PPR fixes;
- general kstuff/jailbreak support;
- support for unofficial modified Encore builds.

Security vulnerabilities should not be filed as normal support requests. Follow
[SECURITY.md](SECURITY.md).
