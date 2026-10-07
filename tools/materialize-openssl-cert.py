#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Materialize Eden's pinned OpenSSL CA bundle from its audited patch.

The pinned Eden snapshot carries .patch/openssl/0001-add-bundled-cert.patch instead of the
post-patch include/openssl/cert.h. PS5 has no normal Unix CA store, so the native build recreates
that exact header in the external OpenSSL include tree and enables Eden's existing
YUZU_BUNDLED_OPENSSL path. No certificate verification is disabled.
"""
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: materialize-openssl-cert.py <eden-cert.patch> <output-cert.h>")

patch = Path(sys.argv[1])
out = Path(sys.argv[2])
text = patch.read_text()
marker = "+++ b/include/openssl/cert.h\n"
if marker not in text:
    raise SystemExit(f"{patch}: bundled cert header patch marker missing")
section = text.split(marker, 1)[1]
lines = []
started = False
for line in section.splitlines():
    if line.startswith("diff --git ") and started:
        break
    if line.startswith("@@"):
        started = True
        continue
    if not started:
        continue
    if line == "-- ":
        break
    if line.startswith("+") and not line.startswith("+++"):
        lines.append(line[1:])
    # Ignore patch metadata/footer lines outside the add-only hunk.

header = "\n".join(lines) + "\n"
if "inline constexpr char kCert[]" not in header:
    raise SystemExit(f"{patch}: kCert declaration missing")
count = header.count("-----BEGIN CERTIFICATE-----")
if count < 100:
    raise SystemExit(f"{patch}: suspiciously small CA bundle ({count} certificates)")

out.parent.mkdir(parents=True, exist_ok=True)
if out.exists() and out.read_text() == header:
    print(f"OpenSSL CA bundle already current: {out} ({count} certificates)")
else:
    tmp = out.with_suffix(out.suffix + ".new")
    tmp.write_text(header)
    tmp.replace(out)
    print(f"Materialized Eden OpenSSL CA bundle: {out} ({count} certificates)")
