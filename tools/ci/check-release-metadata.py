#!/usr/bin/env python3
"""Fast release metadata checks that must pass before the native build."""
from pathlib import Path
import json
import re

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

param = json.loads((root / "sce_sys/param.json").read_text())
assert param.get("titleId") == "PPSA99008", "unexpected title ID"
assert str(param.get("contentId", "")).endswith("PROSPEROEDEN0001"), "unexpected content ID"

workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()
assert "if-no-files-found: error" in workflow, "release artifact upload must fail if files are missing"
assert "[release]" in workflow, "release trigger contract missing"

install = (root / "INSTALL.md").read_text()
assert "Upgrading from ProsperoEden" in install, "legacy migration instructions missing"
assert "FFPFSC" in install and "ZIP" in install, "both installation paths must be documented"

print(f"Release metadata preflight PASS ({tag}, PPSA99008)")
