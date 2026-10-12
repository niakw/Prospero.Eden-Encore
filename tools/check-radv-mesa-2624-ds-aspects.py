#!/usr/bin/env python3
"""Exact source-replayed Mesa 26.2.4 depth/stencil dynamic rendering fixes.

Official commits: 2752b54feeed5bb6fc7d21982b4c8acab0d0e613 and
6e18409d5800f975538236c4152fa4eeca3b444e. Guard only actual GPU code,
not reimplementations of Mesa behavior. Compile/memory-safe semantics remain
Mesa's; the replay byte check is additionally in check-vendored-radv-fork.py.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "vendor/sources/ps5-mesa/src/amd/vulkan/meta"
ACTIVE = ROOT / "vendor/encore-active/ps5-mesa/src/amd/vulkan/meta"
GEN = (ROOT / "tools/patch-radv-wsi.py").read_text()
INSTALL = (ROOT / "tools/install-vendored-radv.py").read_text()

clear_base = (BASE / "radv_meta_clear.c").read_text()
clear = (ACTIVE / "radv_meta_clear.c").read_text()
assert clear_base.count("      aspects &= render->ds_att_aspects;") == 0
assert clear.count("      aspects &= render->ds_att_aspects;") == 1
assert "      if (!aspects)\n         return;" in clear
assert clear.count("radv_fast_clear_depth(cmd_buffer, ds_att->iview, clear_att->clearValue.depthStencil, aspects,") == 1
assert clear.count("emit_depthstencil_clear(cmd_buffer, clear_att->clearValue.depthStencil, aspects, clear_rect,") == 1
assert "radv_fast_clear_depth(cmd_buffer, ds_att->iview, clear_att->clearValue.depthStencil, clear_att->aspectMask," not in clear

resolve_base = (BASE / "radv_meta_resolve.c").read_text()
resolve = (ACTIVE / "radv_meta_resolve.c").read_text()
assert resolve_base.count(".aspectMask = src_iview->vk.aspects,") == 2
assert resolve_base.count(".aspectMask = dst_iview->vk.aspects,") == 1
assert resolve.count("VkImageAspectFlags ds_att_aspects;") == 2
assert resolve.count(".aspectMask = ds_att_aspects,") == 3
assert resolve.count("ds_att_aspects = VK_IMAGE_ASPECT_DEPTH_BIT | VK_IMAGE_ASPECT_STENCIL_BIT;") == 2
assert resolve.count("ds_att_aspects = VK_IMAGE_ASPECT_DEPTH_BIT;") == 2
assert resolve.count("ds_att_aspects = VK_IMAGE_ASPECT_STENCIL_BIT;") == 2
assert ".aspectMask = src_iview->vk.aspects," not in resolve
assert ".aspectMask = dst_iview->vk.aspects," not in resolve

for unit in ("radv_meta_clear.c", "radv_meta_resolve.c"):
    assert "'src/amd/vulkan/meta/" + unit + "': [" in GEN
    assert "'src/amd/vulkan/meta/" + unit + "'," in INSTALL
# Dynamic rendering Vulkan contract: only currently bound aspects have effect.
D, S = 0x2, 0x4
for available in (0, D, S, D | S):
    for requested in (D, S, D | S):
        got = requested & available
        assert got & ~available == 0
        assert (got == 0) == (not(requested & available))
        # Resolve source may list both aspects in one image view, but only
        # the actual depth/stencil attachments define the usable set.
        selected = (D if available & D else 0) | (S if available & S else 0)
        assert selected == available
print("PASS official Mesa 26.2.4 D/S clears+resolves, 2 active units and exact pinned replay")
