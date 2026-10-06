#!/usr/bin/env python3
"""Fast release metadata checks that must pass before the native build."""
from pathlib import Path
import hashlib
import json
import re
import struct

root = Path(__file__).resolve().parents[2]

deps = json.loads((root / "tools/deps.json").read_text())
upstream = json.loads((root / "UPSTREAM.json").read_text())
pins = {item["name"]: item.get("commit") for item in deps["items"] if item.get("commit")}
assert upstream["eden_commit"] == "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
assert upstream["native_template_commit"] == pins["boilerplate"]
assert upstream["ps5_opengl_commit"] == pins["opengl-source"]
assert upstream["ps5_vulkan_commit"] == pins["ps5-vulkan-tools"]
assert upstream["ps5_mesa_commit"] == pins["ps5-mesa"]
assert upstream["ps5_payload_sdk_fork_commit"] == pins["ps5-payload-sdk-fork"]

opengl_builder = (root / "tools/build-opengl-sdk.sh").read_text()
assert pins["opengl-source"] in opengl_builder, "OpenGL builder must lock the audited source commit"
assert "native_boilerplate" in opengl_builder and "manifest.sha256" in opengl_builder, \
    "OpenGL builder must use upstream's pinned toolchain and verify its manifest"
assert "217da45" in opengl_builder and "67c873f" in opengl_builder, \
    "OpenGL audit fixes receipt missing"
cmake = (root / "headless/CMakeLists.txt").read_text()
assert ".local/ps5-opengl-sdk-ad2807d" in cmake, "native target must consume the audited OpenGL SDK"
assert "ps5-opengl-sdk-1.0.1" not in cmake, "old binary OpenGL SDK path returned"
fork_notes = (root / "docs/FORK_NOTES.md").read_text()
assert all(token in fork_notes for token in ("ad2807d", "217da45", "67c873f")), \
    "fork notes must record the audited OpenGL boundary"

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
app = re.search(r'kAppVersion\s*=\s*"([^"]+)"', version_h)
package = re.search(r'kPackageVersion\s*=\s*"([0-9.]+)"', version_h)
assert app and package, "cannot read Encore/package versions"
release = app.group(1)
package_version = package.group(1)

readme = (root / "README.md").read_text()
assert f"## Changes in Encore {release}\n" in readme, f"README missing Changes in Encore {release}"
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
assert hashlib.sha256(logo_bytes).hexdigest() == "c79d0295f42efb053be33c6ad59783306e8165e708ee55a210e33ff2ac5e2d3f", \
    "canonical Encore logo bytes changed unexpectedly"
assert logo_bytes[:8] == b"\x89PNG\r\n\x1a\n", "Encore logo must remain PNG"
assert struct.unpack(">II", logo_bytes[16:24]) == (512, 512), "Encore logo must remain 512x512"
assert not (root / "assets/eden-official.svg").exists(), "obsolete upstream Eden logo must stay removed"
assert not (root / "assets/prosperoeden-icon-source.png").exists(), "obsolete ProsperoEden logo source must stay removed"

background = root / "assets/encore-background.jpg"
assert background.is_file(), "canonical Encore background missing"
assert hashlib.sha256(background.read_bytes()).hexdigest() == "0cf9af8872131c1993dc566a5da46ca370d0354b626dea7d027a455f8a6ad507",     "canonical Encore background bytes changed unexpectedly"
for name, expected_alpha in (("pic0.dds", 3), ("pic1.dds", 1)):
    dds = (root / "assets" / name).read_bytes()
    assert dds[:4] == b"DDS " and dds[84:88] == b"DX10", f"{name} must stay DX10 DDS"
    assert struct.unpack_from("<II", dds, 12) == (2160, 3840), f"{name} must stay 3840x2160"
    assert struct.unpack_from("<I", dds, 128)[0] == 98, f"{name} must stay BC7_UNORM"
    assert struct.unpack_from("<I", dds, 144)[0] == expected_alpha, f"{name} alpha mode changed"

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
assert '-flip' in packager and 'brand.tga' in packager, "launcher logo orientation fix missing"
assert 'encore-background.jpg' in packager and 'backdrop.tga' in packager, "Encore background packaging missing"
assert 'eden-official.svg' not in packager, "packager must not fall back to the old upstream logo"
assert "Prospero.Eden Encore" in packager, "package title-name contract changed"

workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()
assert "if-no-files-found: error" in workflow, "release artifact upload must fail if files are missing"
assert "[release]" in workflow, "release trigger contract missing"

install = (root / "INSTALL.md").read_text()
assert "Upgrading from ProsperoEden" in install, "legacy migration instructions missing"
assert "FFPFSC" in install and "ZIP" in install, "both installation paths must be documented"

preset = (root / "headless/prosperoeden/pe/ui/video_presets.hpp").read_text()
assert "ApplyVideoPreset(Preferences&" in preset and "ApplyVideoPreset(GameSettings&" in preset
assert "{1, 1, 3, 0, 50, 1, 0}" in preset and "{1, 0, 3, 0, 50, 0, 0}" in preset and "{1, 0, 2, 1, 50, 0, 0}" in preset

print(f"Release metadata preflight PASS (Encore {release}, package {package_version}, PPSA99008)")
