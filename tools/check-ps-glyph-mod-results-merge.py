#!/usr/bin/env python3
"""Combined Switch/PC source batches preserve provenance and dedup links."""
import importlib.util
from pathlib import Path

sp=importlib.util.spec_from_file_location(
    "eden_glyph_source_batches",Path(__file__).with_name("ps-glyph-mod-results-merge.py"))
assert sp and sp.loader
m=importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)
def lead(url,provider):
    return {"url":url,"provider":provider,"safety":"UNVERIFIED_SOURCE_LEAD",
            "page_title":"The Game UI Controller mod"}
src={"schema":1,"games":[{"title_id":"01007EF00011E000","game":"BOTW",
      "query":"Switch PlayStation mod",
      "leads":[lead("https://gamebanana.com/mods/659253","duckduckgo")]}]}
pc={"schema":1,"games":[{"title_id":"01007EF00011E000","game":"BOTW",
      "query":"PC PS4 controller mod",
      "leads":[lead("https://gamebanana.com/mods/659253","duckduckgo"),
               lead("https://github.com/test/pc-glyph-port","github")]}]}
final=m.merge([src,pc])
assert final["game_count"]==1
assert final["source_lead_count"]==2
assert len(final["games"][0]["queries"])==2
assert final["games"][0]["mod_pack_ready"] is False
assert final["gameplay_glyphs_autoenabled"]==0
assert final["assets_downloaded"]==0
try:
    m.merge([{"schema":7,"games":[]}])
except ValueError:pass
else:raise AssertionError("accepted unrelated source schema")
print("PASS: batches merge by Switch Title ID, retain multi-console query provenance and never import files")
