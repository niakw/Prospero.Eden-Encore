#!/usr/bin/env python3
"""Synthetic multi-console UI mod -> matching Switch Title ID adaptation routes."""
import importlib.util
from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location("eden_multiplatform_glyph_adapt",
                                          HERE/"ps-glyph-multiplatform-adapt.py")
assert sp and sp.loader
m=importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)

catalog={"schema":1,"games":[
    {"title_id":"01007EF00011E000","title":"The Legend of Zelda: Breath of the Wild",
     "aliases":["The Legend of Zelda: Breath of the Wild"]},
    {"title_id":"0100AAA000111000","title":"Persona 3 Portable","aliases":["Persona 3 Portable"]},
    {"title_id":"0100BBB000111000","title":"Don't Starve Together",
     "aliases":["Don't Starve Together"]},
    {"title_id":"0100CCC000111000","title":"Other Multiplatform Game",
     "aliases":["Other Multiplatform Game"]},
    {"title_id":"0100DDD000111000","title":"Unknown Single Platform Game",
     "aliases":["Unknown Single Platform Game"]},
]}
cross={"schema":1,"sources":[
    {"id":"wii-botw","switch_game":"Zelda: Breath of the Wild",
     "platform":"Wii U","source_url":"https://gamebanana.com/mods/33531",
     "asset_container_family":["SARC","BNTX","Wii U layout"],
     "features":["tutorial controller help","world interaction A"],
     "engine_family":"Nintendo BOTW UI"},
    {"id":"pc-persona","switch_game":"Persona 3 Portable (Switch)",
     "platform":"PC","source_url":"https://gamebanana.com/mods/423178",
     "asset_container_family":["CPK","SPR"],"features":["controller prompts"],
     "engine_family":"Atlus Persona portable"},
    {"id":"ps4-klei","switch_game":"Don't Starve Together",
     "platform":"PC/console Lua mod scripts",
     "source_url":"https://github.com/test/dst-glyphs",
     "asset_container_family":["Klei TEX","Lua","XML atlas"],
     "features":["controller help"],"engine_family":"Klei DST"},
]}
switch={"schema":1,"mods":[
    {"id":"switch-botw","title":"Zelda: Breath of the Wild",
     "source_url":"https://gamebanana.com/mods/659253","rect_xywh":None}
]}
report={"schema":1,"games":[{
    "title_id":"0100CCC000111000","game":"Other Multiplatform Game",
    "leads":[{"url":"https://github.com/fictional/other-pc-button-mod",
              "page_title":"Other Multiplatform Game PC Unreal Engine PAK controller glyphs",
              "provider":"github","safety":"UNVERIFIED_SOURCE_LEAD"}]
}]}
output=m.plan(catalog,cross,switch,[report])
assert output["switch1_title_count"]==5
assert output["games_with_research_mod_sources"]==4
assert output["cross_platform_source_references"]==3
assert output["auto_activated_glyph_packs"]==0
b=output["game_mod_candidates"][0]
assert b["title_id"]=="01007EF00011E000"
assert b["has_same_game_other_platform_mod"] and b["has_native_switch_mod"]
assert len(b["references"])==2
wii=b["references"][0]
assert wii["source_platform"]=="Wii U"
assert wii["switch_route"]=="nintendo_yaz0_sarc_bntx_astc"
assert "ps-glyph-botw-auto-pack.py" in wii["conversion_tools"]
assert wii["input_guest_action_a"]=="ps_cross_if_fixed_eden_ps_profile"
assert wii["controller_right_spatial_icon"]=="ps_circle"
assert not wii["source_binary_directly_switch_compatible"]
assert not wii["ready_to_patch"]
persona=output["game_mod_candidates"][1]
assert persona["references"][0]["switch_route"]=="atlus_cpk_spr"
dst=output["game_mod_candidates"][2]
assert dst["references"][0]["switch_route"]=="klei_atlas_lua"
other=output["game_mod_candidates"][3]
assert other["references"][0]["switch_route"]=="unreal_packages"
assert other["references"][0]["original_source_search_engine"]=="github"
assert output["game_mod_candidates"][4]["needs_discovery"]
assert not output["game_mod_candidates"][4]["references"]
assert m.key("The Legend of Zelda: Breath of the Wild")==m.key("Zelda: Breath of the Wild")
assert m.key("Persona 3 Portable (Switch)")==m.key("Persona 3 Portable")
assert m.key("Hollow Knight: Silksong")!=m.key("Hollow Knight")
assert m.key("Zelda: Breath of the Wild")!=m.key("Zelda: Tears of the Kingdom")
try:
    m.plan(catalog,cross,{"schema":2,"mods":[]})
except ValueError:pass
else:raise AssertionError("bad source schema accepted")
try:
    m.plan({"schema":1,"games":catalog["games"]*2},cross,switch)
except ValueError:pass
else:raise AssertionError("duplicate titleID accepted")

print("PASS: same-game WiiU/PC/PSP and source search mods matched to existing Switch IDs")
print("PASS: console scene/guest-action semantics and engine-specific adapters separated from platform binary compatibility")
print("PASS: other platform sequel not conflated; source candidates never activate gameplay art")
