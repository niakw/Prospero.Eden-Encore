#!/usr/bin/env python3
"""Network-free synthetic regression for all-Switch-1 mod-search discovery."""
from __future__ import annotations
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def load(name, src):
    spec = importlib.util.spec_from_file_location(name, HERE / src)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

corpus = load("eden_glyph_all_switch_title_db", "ps-glyph-switch1-corpus.py")
search = load("eden_glyph_mod_discovery_engine", "ps-glyph-mod-discovery.py")

regions = [
    {"104": {"id": "0100000000010000", "name": "Super Mario Odyssey"},
     "105": {"id": "01007EF00011E000", "name": "The Legend of Zelda: Breath of the Wild"},
     "106": {"id": "040074A01BF12000", "name": "SWITCH 2 exclude"}},
    {"999": {"id": "01007EF00011E000", "name": "Zelda: Breath of the Wild"},
     "998": {"id": "0100000000010000", "name": "Super Mario Odyssey"}},
]
with tempfile.TemporaryDirectory(prefix="eden-glyph-web-discovery-") as root:
    home = Path(root)
    paths = [home / f"region{i}.json" for i in range(2)]
    for file, data in zip(paths, regions):
        file.write_text(json.dumps(data))
    full = corpus.merge(paths, ["Zelda: Breath of the Wild"])
    assert full["game_count"] == 2
    assert full["games"][0]["previously_researched_title"]
    assert full["games"][0]["title"] == "Zelda: Breath of the Wild"
    assert full["glyph_compatible_games"] == 0

    result, st = search.discover(full, {}, 1, network=False)
    assert result["games_examined"] == 1 and not result["source_leads"]
    assert st["next_offset"] == 1 and not st["completed_catalog_scan"]
    assert result["games"][0]["search_links"]["duckduckgo"].startswith(
        "https://duckduckgo.com/?q=")
    assert result["games"][0]["search_links"]["yandex"].startswith(
        "https://yandex.com/search/?text=")
    result2, st2 = search.discover(full, st, 2, network=False, variant=1)
    assert st2["next_offset"] == 2 and st2["completed_catalog_scan"]
    assert result2["games_examined"] == 1

    changed = json.loads(json.dumps(full))
    changed["games"].reverse()
    redone, migrated = search.discover(changed, st, 1)
    assert migrated["catalog_changed_since_last_batch"]
    assert migrated["next_offset"] == 1
    assert redone["games"][0]["title_id"] == changed["games"][0]["title_id"]
    assert search.canonical_link(
        "/l/?uddg=https%3A%2F%2Fgamebanana.com%2Fmods%2F659253&rut=track") == (
        "https://gamebanana.com/mods/659253")
    assert search.canonical_link("https://evil.com/l/?uddg=https%3A%2F%2Fgamebanana.com") is None
    assert search.canonical_link("https://127.0.0.1/secret") is None
    assert search.canonical_link("https://gamebanana.com.evil.net/mods/777") is None
    assert search.canonical_link("javascript:alert(1)") is None
    assert search.canonical_link("http://gamebanana.com/mods/659253?utm_token=secret") == (
        "https://gamebanana.com/mods/659253")

    html = b'<div><a href="/l/?uddg=https%3A%2F%2Fgamebanana.com%2Fmods%2F659253" class="result__a">Zelda Breath of the Wild DS4 controller UI mod</a></div>'
    with patch.object(search, "request_bytes", return_value=html):
        raw = search.ddg("Zelda BOTW mod")
    assert len(raw) == 1
    label = search.candidates_for(
        "Zelda Breath of the Wild", "q", raw, "duckduckgo")
    assert len(label) == 1, label
    assert label[0]["safety"] == "UNVERIFIED_SOURCE_LEAD"
    assert not label[0]["ps5_glyphs_compatible"]
    fake = search.candidates_for(
        "Super Mario Odyssey", "q", raw, "duckduckgo")
    assert fake == [], fake

    with patch.object(search, "ddg", return_value=raw):
        online, newst = search.discover(full, {}, 1, "duckduckgo", network=True,
                                        interval=0)
    assert online["source_leads"] == 1
    assert online["mod_asset_downloads"] == 0
    assert newst["next_offset"] == 1
    assert newst["completed_title_ids"] == [full["games"][0]["title_id"]]
    assert newst["completed_query_keys"] == [
        "duckduckgo|0|" + full["games"][0]["title_id"]]
    # The same Switch1 title MUST be revisited for PC/Wii U/Xbox mods.
    with patch.object(search, "ddg", return_value=raw):
        other, otherstate = search.discover(full, newst, 1, "duckduckgo",
                                           network=True, variant=1, interval=0)
    assert other["games_examined"] == 1
    assert other["games"][0]["title_id"] == full["games"][0]["title_id"]
    assert len(otherstate["completed_query_keys"]) == 2
    with patch.object(search, "ddg", return_value=raw):
        again, already = search.discover(full, otherstate, 1, "duckduckgo",
                                         network=True, variant=0, interval=0)
    assert already["completed_query_keys"] == otherstate["completed_query_keys"]
    assert again["games_examined"] == 1
    assert again["games"][0]["title_id"] != full["games"][0]["title_id"]
    changed_live = json.loads(json.dumps(full))
    changed_live["games"].reverse()
    updated, carried = search.discover(changed_live, newst, 2, network=False)
    assert carried["catalog_changed_since_last_batch"]
    assert carried["completed_title_ids"] == newst["completed_title_ids"]
    assert updated["games_examined"] == 1
    assert updated["games"][0]["title_id"] != newst["completed_title_ids"][0]
    with patch.object(search, "ddg", side_effect=search.ProviderPaused("rate limit")):
        blocked, newstate = search.discover(full, {}, 1, "duckduckgo", True, interval=0)
    assert blocked["games_examined"] == 0 and blocked["errors"]
    assert newstate["next_offset"] == 0

    with patch.object(search, "request_bytes",
                      return_value=json.dumps({"items": [{
                          "full_name": "test/controller-ui-glyphs",
                          "html_url": "https://github.com/test/controller-ui-glyphs"}]}).encode()):
        assert search.github('"Zelda BOTW" controller mod')
    with patch.dict("os.environ", {"YANDEX_SEARCH_API_KEY": "",
                                    "YANDEX_SEARCH_FOLDER_ID": ""}):
        try: search.yandex("game PS5 icons")
        except search.DiscoveryError: pass
        else: raise AssertionError("Yandex charged request attempted without consent/key")

    # Official Yandex API returns base64-encoded XML with results, not
    # an HTML page. Use a fully synthetic response, no paid calls.
    import base64
    xml = b'<response><results><grouping><group><doc><title>Zelda BOTW PS4 button prompts</title><url>https://gamebanana.com/mods/659253</url></doc></group></grouping></results></response>'
    env = {"YANDEX_SEARCH_API_KEY": "TEST-NOT-LIVE",
           "YANDEX_SEARCH_FOLDER_ID": "TEST"}
    with patch.dict("os.environ", env), patch.object(
        search, "request_bytes",
        return_value=json.dumps({"rawData": base64.b64encode(xml).decode()}).encode()):
        assert search.yandex("Zelda") == [
            ("Zelda BOTW PS4 button prompts", "https://gamebanana.com/mods/659253")]

    # Exactly one roundtrip state write, no overwrite without explicit rotate.
    search.new_file(home / "batch.json", result)
    assert json.loads((home / "batch.json").read_text())["catalog_total"] == 2
    try: search.new_file(home / "batch.json", result)
    except search.DiscoveryError: pass
    else: raise AssertionError("overwritten previous evidence report")

print("PASS: 2-region dedup Switch base games, repeatable resumable offsets and stale catalog rejection")
print("PASS: DDG/Yandex XML/GitHub safe source URL parsing, no billed API calls, rate-limit preserves cursor")
print("PASS: all source leads unverified, no game assets downloaded or title compatibility claimed")
