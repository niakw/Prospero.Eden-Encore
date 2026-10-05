#!/usr/bin/env python3
"""Fast release gate for Encore's 13.60 startup/elevation/storage contract."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "headless/main.cpp").read_text()
elevation = (root / "headless/elevation/elevation.cpp").read_text()
helper = (root / "headless/elevation/helper/main.cpp").read_text()
packager = (root / "tools/package-headless-native.sh").read_text()
lifecycle = (root / "src/lifecycle.c").read_text()

body = main[main.index("int main("):]
boot = body.index("BootTrace::Begin")
request = body.index("elevation::request")
migrate_sandbox = body.index("MigrateSandboxData")
migrate_legacy = body.index("MigrateLegacyInstallAssets")
assert boot < request < migrate_sandbox < migrate_legacy
for forbidden in ("std::thread", "std::jthread", "pthread_create"):
    assert forbidden not in body[:request], f"{forbidden} starts before the one-shot helper"

assert "ProbeWritableRoot(Eden::kDataDir)" in body
assert body.index("MigrateLegacyInstallAssets") < body.index("PrepareStorageLayout();") < body.index("BootTrace::Ready")
assert "invalid_success_identity" not in body, "uid/gid inference must not kill a valid filesystem grant"
assert 'target_title_id[] = "PPSA99008"' in helper
assert 'sandbox-elevator.elf' in packager
assert 'PPSA99121' not in lifecycle, "stale lifecycle title ID"
assert 'PPSA99008' in lifecycle

for stage in (
    "elevation: request begin",
    "elevation: connect 127.0.0.1:9021",
    "elevation: helper stream complete",
    "elevation: prepare received",
    "elevation: final response",
):
    assert stage in elevation, f"missing startup trace stage: {stage}"

print("Startup contract: trace, single-threaded elevation, real filesystem proof and title identity PASS")
