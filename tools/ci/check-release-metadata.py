#!/usr/bin/env python3
"""Fast release metadata checks that must pass before the native build."""
from pathlib import Path
import hashlib
import re
import struct

root = Path(__file__).resolve().parents[2]

required = [
    "README.md",
    "INSTALL.md",
    "SECURITY.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
]
missing = [name for name in required if not (root / name).is_file()]
assert not missing, f"missing release/community files: {missing}"

version_h = (root / "headless/prosperoeden/version.h").read_text()
m = re.search(r'kAppVersion\s*=\s*"([0-9.]+)"', version_h)
assert m, "cannot read kAppVersion"
version = m.group(1)
tag = "v" + version.removeprefix("0")

readme = (root / "README.md").read_text()
assert f"## Changes in {tag}\n" in readme, f"README missing Changes in {tag}"
assert "[INSTALL.md](INSTALL.md)" in readme, "README must link INSTALL.md"
assert "[SECURITY.md](SECURITY.md)" in readme, "README must link SECURITY.md"
assert "GPL-3.0-or-later" in readme, "README must state GPL-3.0-or-later"
assert 'src="assets/icon0.png"' in readme, "README must use the Encore package logo"

logo = root / "assets/icon0.png"
packaged_logo = root / "sce_sys/icon0.png"
assert logo.is_file(), "canonical Encore logo missing"
assert packaged_logo.is_file(), "source sce_sys Encore logo missing"
logo_bytes = logo.read_bytes()
assert logo_bytes == packaged_logo.read_bytes(), "repo and package Encore logos diverged"
assert hashlib.sha256(logo_bytes).hexdigest() == "2364c92807866e304706a437db47ec5927edb341186c5495d04b18f496711204", \
    "canonical Encore logo bytes changed unexpectedly"
assert logo_bytes[:8] == b"\x89PNG\r\n\x1a\n", "Encore logo must remain PNG"
assert struct.unpack(">II", logo_bytes[16:24]) == (512, 512), "Encore logo must remain 512x512"
assert not (root / "assets/eden-official.svg").exists(), "obsolete upstream Eden logo must stay removed"
assert not (root / "assets/prosperoeden-icon-source.png").exists(), "obsolete ProsperoEden logo source must stay removed"

lifecycle = (root / "src/lifecycle.c").read_text()
assert "PPSA99121" not in lifecycle, "stale lifecycle title ID"
assert "PPSA99008" in lifecycle, "lifecycle must name Encore's title ID"

startup = (root / "headless/main.cpp").read_text()
assert "ProbeWritableRoot(Eden::kDataDir)" in startup, "release must prove /data/prosperoeden before migration"
assert "invalid_success_identity" not in startup, "release must not infer filesystem capability from uid/gid alone"

packager = (root / "tools/package-headless-native.sh").read_text()
assert "titleId='PPSA99008'" in packager, "packager title ID contract changed"
assert "PROSPEROEDEN0001" in packager, "packager content ID contract changed"
assert 'assets/icon0.png' in packager, "packager must use the Encore raster logo"
assert 'eden-official.svg' not in packager, "packager must not fall back to the old upstream logo"
assert "Prospero.Eden Encore" in packager, "package title-name contract changed"

workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()
assert "if-no-files-found: error" in workflow, "release artifact upload must fail if files are missing"
assert "[release]" in workflow, "release trigger contract missing"

install = (root / "INSTALL.md").read_text()
assert "Upgrading from ProsperoEden" in install, "legacy migration instructions missing"
assert "FFPFSC" in install and "ZIP" in install, "both installation paths must be documented"

print(f"Release metadata preflight PASS ({tag}, PPSA99008)")
