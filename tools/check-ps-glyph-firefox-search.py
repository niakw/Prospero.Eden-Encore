#!/usr/bin/env python3
"""No-network tests for read-only Firefox DDG/Yandex public result pages."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location(
    "eden_firefox_public_pages",Path(__file__).with_name("ps-glyph-firefox-search.py"))
assert spec and spec.loader
fx=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fx)

assert fx.engine_url("firefox_duckduckgo", "Zelda PS icons").startswith(
    "https://duckduckgo.com/?q=")
assert fx.engine_url("firefox_yandex", "Zelda кнопки").startswith(
    "https://yandex.com/search/?text=")
assert fx.matching_engine("sub.yandex.com","firefox_yandex")
assert not fx.matching_engine("yandex.com.evil.invalid","firefox_yandex")
links=[
    {"href":"https://gamebanana.com/mods/659253",
     "text":"Zelda BOTW controller mod"},
    {"href":"https://yandex.com/suggest","text":"Yandex suggestions"},
    {"href":"https://github.com/test/ps4-icons","text":"Another controller mod"},
]
result=fx.evaluate_page("firefox_yandex",
                        "https://yandex.com/search/?text=Zelda",
                        "Yandex Search","Zelda BOTW PlayStation controller mods",
                        links,200)
assert len(result)==2
assert result[0][1]=="https://gamebanana.com/mods/659253"

for provider,url,title,body,status in [
    ("firefox_duckduckgo","https://duckduckgo.com/?q=Zelda",
     "CAPTCHA required","",200),
    ("firefox_duckduckgo","https://duckduckgo.com/?q=Zelda",
     "Results","unusual traffic, are you human?",200),
    ("firefox_yandex","https://yandex.com/search/?text=test",
     "Проверка браузера","Не робот",200),
    ("firefox_duckduckgo","https://duckduckgo.com/?q=test",
     "Search Results","",429),
    ("firefox_yandex","https://evil.invalid/redirect",
     "Search Results","",200),
]:
    try:
        fx.evaluate_page(provider,url,title,body,links,status)
    except fx.FirefoxSearchPaused:
        pass
    else:
        raise AssertionError("attempted to bypass/refuse invalid search page: "+title)

# Browser search is dispatched only when explicit Firefox mode is selected.
dsp=importlib.util.spec_from_file_location(
    "eden_firefox_dispatch",Path(__file__).with_name("ps-glyph-mod-discovery.py"))
assert dsp and dsp.loader
mod=importlib.util.module_from_spec(dsp)
dsp.loader.exec_module(mod)
catalog={"schema":1,"games":[{"title_id":"01007EF00011E000",
                            "title":"Zelda: Breath of the Wild"}]}
seen=[]
def search(name,query):
    seen.append((name,query))
    return [("Zelda Breath of the Wild PS4 controller mod",
             "https://gamebanana.com/mods/659253")]
batch,state=mod.discover(catalog,{},1,provider="firefox_duckduckgo",
                         network=True,variant=0,interval=0,browser_search=search)
assert len(seen)==1 and batch["source_leads"]==1
assert state["completed_query_keys"]==["firefox_duckduckgo|0|01007EF00011E000"]
def paused(*args):
    raise mod.ProviderPaused("challenge displayed")
bad,old=mod.discover(catalog,{},1,provider="firefox_yandex",
                     network=True,variant=3,interval=0,browser_search=paused)
assert len(bad["errors"])==1 and old["completed_query_keys"]==[]
print("PASS browser public result parsing, Firefox explicit opt-in and challenge stop")
print("PASS no actual search network or paid Yandex account used")
