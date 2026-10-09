#!/usr/bin/env python3
"""Synthetic Lua controller art/label static scanner regression.

No game binaries, scripts executed, or PS5 graphic runtime. This fixture
is source-added only, not executed without user approval.
"""
from __future__ import annotations
import importlib.util
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("eden_lua_glyph_static",ROOT/"tools/ps-glyph-lua-source-inspect.py")
assert spec and spec.loader
scanner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)

source="""local LEFT_SIDE = -415
local RIGHT_SIDE = 415
local LABEL_WIDTH = 320
local LABEL_HEIGHT = 50
if IsPS4() then
  Asset("ATLAS", "images/ps4_controllers.xml")
  Asset("IMAGE", "images/ps4_controllers.tex")
elseif IsSWITCH() then
  Asset("ATLAS", "images/nx_controllers.xml")
  Asset("IMAGE", "images/nx_controllers.tex")
end
local LABELS = {
  [DEVICE_DUALSHOCK4] = {
    { x = 20, y = 275, anchor = ANCHOR_RIGHT, text = STRINGS.UI.CONTROLSSCREEN.PS4.TOUCHPAD },
    { x = RIGHT_SIDE, y = -20, anchor = ANCHOR_LEFT, text = STRINGS.UI.CONTROLSSCREEN.PS4.CROSS },
  },
  [DEVICE_SWITCH] = {
    { x = LEFT_SIDE, y = 80, anchor = ANCHOR_RIGHT, text = STRINGS.UI.CONTROLSSCREEN.PS4.L1 },
  }
}
if v.anchor == ANCHOR_RIGHT then
  label:SetPosition(v.x - LABEL_WIDTH/2 - 8, v.y, 0)
else
  label:SetPosition(v.x + LABEL_WIDTH/2, v.y, 0)
end
-- G.CONTROLLER.get_console_from_gamepad() ignored in comment
function G.CONTROLLER.get_console_from_gamepad(gamepad)
  return 'Playstation'
end
"""
with tempfile.TemporaryDirectory(prefix="eden-lua-glyph-scan-") as temp:
    file=Path(temp)/"optionsscreen.lua"
    file.write_text(source,encoding="utf-8")
    result=scanner.inspect(file)
    assert len(result["controller_asset_references"]) == 4
    assert len(result["controller_help_label_rows"]) == 3
    labels=result["controller_help_label_rows"]
    assert labels[0]["local_label_widget_x_if_formula_applies"] == -148
    assert labels[1]["local_label_widget_x_if_formula_applies"] == 575
    assert labels[2]["local_label_widget_x_if_formula_applies"] == -583
    assert labels[0]["device"] == "DUALSHOCK4"
    assert labels[2]["device"] == "SWITCH"
    assert any(x["uses_console_selection_api"] for x in
               result["possible_runtime_controller_style_selectors"])
    assert result["original_switch_binary_verified"] is False
    assert result["atlas_sprite_uv_rectangles_verified"] is False

    file.write_bytes(b"\x00" + source.encode("utf-8"))
    try:
        scanner.inspect(file)
    except ValueError:
        pass
    else:
        raise AssertionError("Lua NUL binary mistakenly accepted")

print("HOST FIXTURE PASS: static Lua controller assets, style hooks and label widget positions")
print("No Lua/game execution and no actual Switch atlas coordinates")
