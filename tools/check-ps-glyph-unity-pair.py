#!/usr/bin/env python3
"""Synthetic metadata-only PC/Switch Unity Sprite pairing fixture.

Intentionally not executed during the user no-build/no-run gate.
"""
from __future__ import annotations
import importlib.util

from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eden_unity_pair_metadata", ROOT / "tools/ps-glyph-unity-pair.py")
assert spec and spec.loader
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

PC = {"schema":1,"source":"unity_serialized_asset_metadata",
      "container_sha256":"a"*64, "source_platform_declared":"PC",
      "objects":[
          {"object_type":"Texture2D", "name":"btn_cross",
           "texture_dimensions":[128,128],"path_id":45},
          {"object_type":"Sprite", "name":"controller_cross",
           "serialized_sprite_rect":[0,0,28,28],
           "serialized_texture_rect":[64,32,28,28], "path_id":64},
          {"object_type":"Texture2D", "name":"PS5_buttons",
           "texture_dimensions":[256,256], "path_id":47},
      ]}
NX = {"schema":1,"source":"unity_serialized_asset_metadata",
      "container_sha256":"b"*64, "source_platform_declared":"Switch",
      "objects":[
          {"object_type":"Texture2D", "name":"btn_cross",
           "texture_dimensions":[128,128],"path_id":145},
          {"object_type":"Sprite", "name":"controller_cross",
           "serialized_sprite_rect":[0,0,28,28],
           "serialized_texture_rect":[120,16,28,28], "path_id":164},
      ]}
result = tool.compare(PC, NX)
assert result["shared_object_name_count"] == 2
assets = {v["name"]:v for v in result["shared_name_candidates"]}
assert assets["btn_cross"]["declared_geometry_equal"] is True
assert assets["controller_cross"]["declared_geometry_equal"] is False
assert assets["controller_cross"]["pc_geometry"] == [64,32,28,28]
assert assets["controller_cross"]["switch_geometry"] == [120,16,28,28]
assert result["pc_only_playstation_named_assets"][0]["name"] == "PS5_buttons"
assert result["actual_switch_ps_texture_pixels_verified"] == 0
NX["objects"].append({"object_type":"Sprite","name":"controller_cross",
                       "serialized_texture_rect":[40,20,28,28]})
result = tool.compare(PC, NX)
assert {v["name"]:v for v in result["shared_name_candidates"]}[
    "controller_cross"]["status"] == "ambiguous_duplicate_object_names"
assert result["ps5_qualified"] is False
print("HOST FIXTURE PASS: Unity object pairing, sprite rect position and ambiguous names")
print("No game texture data or console qualification tested")
