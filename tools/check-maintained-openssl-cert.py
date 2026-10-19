#!/usr/bin/env python3
"""OpenSSL CA bundle: maintained-source identity and atomic stage oracle.

This checks only provenance and byte-preservation. No host TLS network
probe, native firmware or end-to-end certificate-chain proof is claimed.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
maintained = root / "vendor/encore-active/eden-build/openssl/cert.h"
original = root / "vendor/sources/eden/.patch/openssl/0001-add-bundled-cert.patch"
script = root / "tools/materialize-openssl-cert.py"
build = (root / "tools/build-headless-native.sh").read_text()
assert 'materialize-openssl-cert.py' in build
source = maintained.read_bytes()
assert source.startswith(b"#ifndef CERT_H_\n#define CERT_H_")
assert b"inline constexpr char kCert[]" in source
assert source.count(b"-----BEGIN CERTIFICATE-----") == 147
assert source.count(b"-----END CERTIFICATE-----") == 147
assert b"CURLOPT_SSL_VERIFYPEER" not in source
assert 'source.read_bytes()' in script.read_text()
assert 'legacy != header' in script.read_text()
with tempfile.TemporaryDirectory(prefix="encore-ca-stage-") as directory:
    temp = Path(directory)
    staged = temp / "include/openssl/cert.h"
    args = [sys.executable, "-B", str(script), str(original), str(staged)]
    for i in range(2):
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert staged.read_bytes() == source
    # A tampered pinned patch must not silently change the versioned trust
    # material. The build aborts rather than changing the CA chain.
    corrupted = temp / "invalid.patch"
    corrupted.write_bytes(original.read_bytes().replace(
        b"-----BEGIN CERTIFICATE-----", b"-----BEGIN ALTERED CERT-----", 1))
    bad = subprocess.run([sys.executable, "-B", str(script),
                          str(corrupted), str(staged)],
                         capture_output=True, text=True, timeout=20)
    assert bad.returncode != 0 and staged.read_bytes() == source
print("ENCORE_MAINTAINED_OPENSSL_CA_SOURCE_PASS certificates=147 "
      "staged_identical=1 pinned_patch_parity=1 negative_test=1")
