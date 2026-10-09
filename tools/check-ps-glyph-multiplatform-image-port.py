#!/usr/bin/env python3
"""Synthetic same-game PC/WiiU different-art Switch glyph position recovery."""
from __future__ import annotations
import importlib.util
import tempfile
from pathlib import Path
from PIL import Image,ImageDraw

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location("eden_multiplatform_image_port",
                                          HERE/"ps-glyph-multiplatform-image-port.py")
assert sp and sp.loader
m=importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)

with tempfile.TemporaryDirectory(prefix="eden-multiplatform-glyph-") as dir:
    home=Path(dir)
    pc=home/"button_a_original.png"
    patched=home/"button_a.png"
    switch=home/"source_switch.png"
    original=Image.new("RGBA",(80,64),(0,0,0,0))
    ImageDraw.Draw(original).rectangle((20,15,39,34),fill=(255,0,0,255))
    changed=original.copy()
    ImageDraw.Draw(changed).rectangle((22,17,37,32),fill=(5,199,210,255))
    nx=Image.new("RGBA",(160,128),(0,0,0,0))
    ImageDraw.Draw(nx).ellipse((40,30,79,69),fill=(20,240,30,255))
    original.save(pc)
    changed.save(patched)
    nx.save(switch)
    result=m.draft(pc,patched,switch,"01007EF00011E000","1.6.0",
                   "Wii U","world_interaction","Layout/Menu.png")
    assert result["source_platform"]=="Wii U"
    assert result["relative_positions_recovered"]==1
    assert result["slots"][0]["rect"]==[38,28,44,44]
    assert result["slots"][0]["kind"]=="guest_action"
    assert result["slots"][0]["guest_button"]=="a"
    assert result["slots"][0]["reviewed"] is False
    assert result["ready_to_install"] is False
    assert result["source_mod_art_redistributed"] is False
    assert result["same_game_positions_without_equal_art_supported"] is True
    assert result["exact_same_art_component_positions"]==[]
    moved=Image.new("RGBA",(160,128),(0,0,0,0))
    ImageDraw.Draw(moved).ellipse((110,80,149,119),fill=(0,240,30,255))
    moved.save(switch)
    no=m.draft(pc,patched,switch,"01007EF00011E000","1.6.0",
               "Wii U","world_interaction","Layout/Menu.png")
    assert no["relative_positions_recovered"]==0
print("PASS: multiplatform mod different assets+resolution transfer only source-backed matching Switch glyph coordinates")
print("PASS: guest action hints remain review-only; shifted/unrelated original Switch sprites not patched")
