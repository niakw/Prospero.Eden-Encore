# Security Policy

Prospero.Eden Encore is a PS5 homebrew emulator port that contains native code, file import/export
logic, build tooling and a privileged one-shot filesystem-elevation helper. Security reports for
those areas are taken seriously.

## Supported versions

| Version / branch | Security support |
| --- | --- |
| Current **Prospero.Eden Encore 1.000.040** release line | ✅ Supported |
| Default branch `fix/0.40-zbic-13.60` | ✅ Supported |
| Archive/reference branch `>0.50-bug_13.60` | ❌ Not supported |
| Upstream ProsperoEden / Eden | ❌ Report to the corresponding upstream project |

Encore's primary validated console target is **PS5 firmware 13.60**. A security issue may still be
relevant on another firmware, but firmware compatibility itself is not a security guarantee.

## Reporting a vulnerability

Please **do not open a public issue, discussion or pull request containing exploitable details**.

Preferred reporting path:

1. Open this repository's **Security** tab.
2. Choose **Advisories / Report a vulnerability** when private vulnerability reporting is
   available.
3. Include enough information to reproduce and understand the impact.

If private vulnerability reporting is unavailable, contact the repository owner **@niakw**
privately through a contact method listed on the maintainer's GitHub profile rather than publishing
the exploit details.

A useful report includes:

- affected Encore commit/release;
- PS5 firmware and relevant jailbreak/runtime environment;
- affected file/component;
- impact and required attacker/user interaction;
- minimal reproduction steps or proof of concept;
- crash log / boot trace when relevant;
- whether keys, saves, arbitrary files, elevated credentials or release artifacts can be exposed or
  modified.

Please remove personal data, console identifiers, keys, copyrighted game content and unrelated
secrets from reports.

## Security-relevant areas

Reports are especially useful for:

- **Elevation / sandbox escape**
  - wrong-process or wrong-title targeting;
  - credential corruption;
  - privilege persistence beyond the intended one-shot helper;
  - protocol validation bypass;
  - rollback failures that leave an unintended partially modified state.

- **Filesystem and save handling**
  - path traversal;
  - symlink/hardlink escapes;
  - arbitrary read/write/delete outside a selected import/export/data tree;
  - unsafe archive or package extraction.

- **Memory safety / native code**
  - exploitable out-of-bounds access;
  - use-after-free;
  - double free;
  - attacker-controlled command execution;
  - unsafe handling of malformed metadata or content.

- **Build and release supply chain**
  - dependency checksum/pin bypass;
  - malicious or replaceable release inputs;
  - GitHub Actions privilege escalation;
  - artifact poisoning;
  - forged or mismatched release assets/checksums.

- **Secrets / sensitive data**
  - committed credentials or tokens;
  - accidental inclusion of console keys, firmware, saves or private data in build artifacts/logs;
  - crash reports containing memory contents or secrets.

## Elevation security model

Encore intentionally keeps the ProsperoEden 1.000.040 one-request filesystem-elevation design
instead of the newer Lapy path.

The current helper:

- is packaged for the exact title ID `PPSA99008`;
- accepts only the `filesystem` capability;
- uses a fixed versioned protocol;
- validates the target PID/title;
- requires a cloned credential before modification;
- reads back and verifies the complete resulting state;
- attempts to restore and verify the original state after an apply failure;
- uses bounded local transport timeouts;
- handles one request and exits instead of installing a persistent privilege service.

This reduces attack surface and failure modes but **does not create a least-privilege sandbox after
successful elevation**. Filesystem escape still requires broad process credentials/capabilities.
The jailbreak environment and local ELF loader are therefore part of the trusted computing base.

Implementation details are documented in
[`headless/elevation/README.md`](headless/elevation/README.md).

## Out of scope

Unless they reveal a separate security vulnerability in Encore, the following are not security
reports for this repository:

- game compatibility or performance regressions;
- emulator accuracy differences;
- PS5 FPKG entitlement/PPR problems;
- kstuff/jailbreak bugs outside Encore;
- vulnerabilities that exist only in a modified unofficial build;
- availability of copyrighted games, keys or firmware.

FPKG/kstuff support on firmware 13.60 is an external jailbreak/runtime concern and is not claimed to
be implemented or repaired by Encore.

## Coordinated disclosure

Please allow the maintainer to reproduce, patch and validate a vulnerability before publishing
technical exploitation details. Once a fix is available, a GitHub Security Advisory can be used to
document affected versions, severity and remediation where appropriate.

There is no guaranteed response-time SLA for this personal open-source project, but valid reports
will be prioritized according to exploitability and impact.

## Repository security controls

The repository uses or is designed to use:

- GitHub CodeQL scanning for Actions, C/C++ and Python;
- least-privilege GitHub Actions permissions;
- pinned build dependencies with cryptographic hashes or immutable commits;
- pinned GitHub Actions revisions;
- reproducible release packaging and SHA-256 checksums;
- release publication only after a successful shipping build;
- explicit Git ignores for keys, ROM/container files and local save-transfer data;
- save-import symlink rejection and regression tests.

No keys, firmware, games or proprietary console data should ever be committed to this repository.
