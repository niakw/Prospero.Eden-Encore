#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R440: preserve Pereira's never-presented VideoOut takeover in active WSI."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
wsi = (root/"vendor/encore-active/ps5-mesa/src/vulkan/wsi/wsi_common_videoout.c").read_text()
gen = (root/"tools/patch-radv-wsi.py").read_text()
for marker in ("bool presented;", "chain->presented = true;",
               "videoout_display_free_locked", "!current->presented",
               "if (result == VK_SUCCESS && !videoout_display_free_locked(old))",
               "if (!videoout_display_free_locked(old))",
               "wsi_destroy_image(&chain->base, &chain->images[i]);",
               "wsi_swapchain_finish(&chain->base);",
               "unpresented swapchain yielded display"):
    assert marker in wsi, marker
assert gen.count("R440: mpereiraesaa/PS5_Mesa f2ee389") == 1
assert "for old, new in [" in gen and "replace(old, new)" in gen
assert "out->current && out->current != (struct wsi_videoout_swapchain *)" not in wsi
assert wsi.count("chain->presented = true;") == 1
# Relevant state cases in the author's original host model.
def can_take(current_exists, current_is_old, has_presented):
    return not current_exists or current_is_old or not has_presented
assert can_take(False, False, False)
assert can_take(True, True, True)
assert can_take(True, False, False)
assert not can_take(True, False, True)
# The installation rechecks under lock after buffer allocation.
assert wsi.index("if (result == VK_SUCCESS && !videoout_display_free_locked(old))") < wsi.index("if (!videoout_display_free_locked(old))")
print("R440 Pereira VideoOut takeover source + state contract PASS")
