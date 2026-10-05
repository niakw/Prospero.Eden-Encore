#!/usr/bin/env python3
"""Fast contract checks for Encore's self-contained no-elevation storage mode."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "headless/main.cpp").read_text()
storage = (root / "headless/storage_paths.h").read_text()
assets = (root / "headless/assets_dir.h").read_text()
bridge = (root / "headless/metadata_bridge.cpp").read_text()
services = (root / "headless/prosperoeden/eden_services.cpp").read_text()
browse = (root / "headless/prosperoeden/pe/ui/browse.cpp").read_text()

assert "kFilesystemSelfContained = -2" in storage
assert "SelfContainedMode()" in storage
assert 'ConfigDir() + "/backup"' in storage
assert 'ConfigDir() + "/save-export"' in storage

assert 'FileExists("/app0/self-contained.txt")' in assets

detect = main.index("SelfContainedModeRequested()")
request = main.index("elevation::request(elevation::Capability::filesystem)")
assert detect < request, "self-contained detection must happen before elevation"
assert "filesystem elevation skipped" in main
assert 'Eden::UserDir() + "/cache"' in main, "sandbox RADV cache must use writable storage"

assert "Eden::BackupDir()" in bridge
assert "Eden::ExportDir()" in bridge

assert "if (Eden::SelfContainedMode())" in services
assert "return directory == Eden::AssetsDir();" in services
assert "access == -2 ? tr("Sandbox only")" in browse

print("Self-contained storage contract PASS: explicit marker, fixed app assets, sandbox writes, no elevation request")
