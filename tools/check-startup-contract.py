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

# The rotating 3D jacket is the only authored startup animation. Both
# render backends retain their warm-up presentations but show a plain
# dark handoff, NOT the obsolete violet loading shader.
vulkan_loading = (root / "headless/vulkan_hud.frag").read_text()
graphics = (root / "headless/graphics.cpp").read_text()
vulkan_backend = (root / "vendor/encore-active/eden-vulkan/vulkan_renderer.cpp").read_text()
assert 'color = vec4(0.024, 0.035, 0.039, 1.0);' in vulkan_loading
assert 'loading_scene(' not in vulkan_loading
assert 'PresentVulkanLoading(renderer);' in graphics
assert 'PresentLoading();' in vulkan_backend
assert '"void main(){ color = vec4(0.024, 0.035, 0.039, 1.0); }\\n";' in graphics

for stage in (
    "elevation: request begin",
    "elevation: connect 127.0.0.1:9021",
    "elevation: helper stream complete",
    "elevation: prepare received",
    "elevation: final response",
):
    assert stage in elevation, f"missing startup trace stage: {stage}"

print("Startup contract: trace, single-threaded elevation, real filesystem proof and title identity PASS")
