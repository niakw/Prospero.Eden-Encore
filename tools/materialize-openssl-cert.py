#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage Encore's maintained, pinned OpenSSL CA certificate header.

The pinned upstream patch is a parity oracle ONLY. Native builds copy the
complete source maintained under vendor/encore-active; no C++ header is
constructed by source transformations in the build script. Keep the
existing bundled certificate verification semantics unchanged.
"""
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: materialize-openssl-cert.py <eden-cert.patch> <output-cert.h>")

root = Path(__file__).resolve().parents[1]
source = root / "vendor/encore-active/eden-build/openssl/cert.h"
patch = Path(sys.argv[1])
out = Path(sys.argv[2])
if not source.is_file():
    raise SystemExit(f"Missing canonical Encore CA source: {source}")
header = source.read_bytes()
text = patch.read_text()
marker = "+++ b/include/openssl/cert.h\n"
if text.count(marker) != 1:
    raise SystemExit(f"{patch}: bundled cert header patch marker missing or ambiguous")
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
legacy = ("\n".join(lines) + "\n").encode("utf-8")
if legacy != header:
    raise SystemExit(f"{patch}: canonical Encore certificate header differs from pinned upstream")
cert_count = header.count(b"-----BEGIN CERTIFICATE-----")
if cert_count < 100 or b"inline constexpr char kCert[]" not in header:
    raise SystemExit(f"{source}: invalid or unexpectedly small CA bundle")
out.parent.mkdir(parents=True, exist_ok=True)
if out.exists() and out.read_bytes() == header:
    print(f"Maintained OpenSSL CA header already current: {out} ({cert_count} certificates)")
else:
    tmp = out.with_suffix(out.suffix + ".new")
    tmp.write_bytes(header)
    tmp.replace(out)
    print(f"Copied maintained OpenSSL CA source: {out} ({cert_count} certificates)")
