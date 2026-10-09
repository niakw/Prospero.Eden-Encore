#!/usr/bin/env python3
"""Host-only all-title four-console-variant search queue regression."""
import importlib.util
from pathlib import Path

path=Path(__file__).with_name("ps-glyph-switch1-search-queue.py")
spec=importlib.util.spec_from_file_location("eden_queue_test",path)
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
catalog={"schema":1,"games":[
    {"title_id":"01007EF00011E000","title":"Zelda: Breath of the Wild"},
    {"title_id":"0100AAA000111000","title":"Persona 3 Portable"}]}
out=m.queue(catalog)
assert out["distinct_game_title_ids"]==2
assert out["total_search_tasks"]==8
first=out["games"][0]["queries"]
assert len(first)==4
assert first[0]["platform_scope"]=="Switch"
assert "WiiU" in first[1]["platform_scope"]
assert "site:gamebanana.com" in first[2]["query"]
assert "кнопки" in first[3]["query"]
assert all(x["providers"]["duckduckgo"].startswith("https://duckduckgo.com/?q=")
           for x in first)
assert all(x["providers"]["yandex"].startswith("https://yandex.com/search/?text=")
           for x in first)
assert all(not x["source_mod_identified"] for x in first)
assert out["mod_downloads"]==0
print("PASS: all-title/console/region variants generate standalone rate-limit-friendly source queries")
