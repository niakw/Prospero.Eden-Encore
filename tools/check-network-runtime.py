#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""PS5 HTTPS uses Eden's complete pinned CA bundle and Encore identifies Nlib requests."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
build = (root / "tools/build-headless-native.sh").read_text()
materialize = (root / "tools/materialize-openssl-cert.py").read_text()
patch = (root / "headless/backports/eden-ps5-net-user-agent.patch").read_text()
apply = (root / "tools/apply-eden-backports.sh").read_text()

assert "YUZU_BUNDLED_OPENSSL=1" in cmake
assert "materialize-openssl-cert.py" in build
assert ".patch/openssl/0001-add-bundled-cert.patch" in build
assert "inline constexpr char kCert[]" in materialize
assert 'count < 100' in materialize
assert "Prospero.Eden-Encore/1" in patch
assert 'request.headers.emplace("User-Agent"' in patch
assert "BEGIN CERTIFICATE" not in patch
assert "eden-ps5-net-user-agent.patch" in apply
print("Encore PS5 HTTPS/Nlib CA + HTTP identity contract PASS")
