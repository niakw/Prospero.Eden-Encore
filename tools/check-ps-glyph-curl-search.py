#!/usr/bin/env python3
"""No-network tests: curl Firefox UA, DDG/Yandex links and refusal policy."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location(
    "eden_curl_search_test",Path(__file__).with_name("ps-glyph-curl-search.py"))
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert "Firefox/" in mod.FIREFOX_UA
assert mod.engine_url("curl_duckduckgo","BOTW PS4").startswith(
    "https://html.duckduckgo.com/html/?q=")
assert mod.engine_url("curl_yandex","BOTW кнопки").startswith(
    "https://yandex.com/search/?text=")
html=b'<html><body><a class="result__a" href="/l/?uddg=https%3A%2F%2Fgamebanana.com%2Fmods%2F659253">Zelda BOTW DS4 mod</a><a href="https://github.com/test/botw-controller-buttons">BOTW controller glyphs</a></body></html>'
a=mod.parse_page("curl_duckduckgo","https://html.duckduckgo.com/html/?q=BOTW",
                 "https://html.duckduckgo.com/html/?q=BOTW",200,html)
assert len(a)==2 and "gamebanana.com" in a[0][1]
b=mod.parse_page("curl_yandex","https://yandex.com/search/?text=BOTW",
                 "https://yandex.com/search/?text=BOTW",200,html)
assert len(b)==2
for status,body,where in [
    (403,html,"https://html.duckduckgo.com/html/"),
    (429,html,"https://html.duckduckgo.com/html/"),
    (200,b"CAPTCHA. Verify you are human","https://html.duckduckgo.com/html/"),
    (200,html,"https://evil.invalid/login")
]:
    try:mod.parse_page("curl_duckduckgo","https://html.duckduckgo.com/",
                       where,status,body)
    except mod.CurlSearchPaused:pass
    else:raise AssertionError("illegal source accepted")
marker=b"\nEDEN_SEARCH_HTTP:200\nEDEN_SEARCH_URL:https://html.duckduckgo.com/html/?q=BOTW\n"
with patch.object(mod.subprocess,"run",
                  return_value=SimpleNamespace(returncode=0,stdout=html+marker,stderr=b"")) as run:
    result=mod.search("curl_duckduckgo","BOTW")
    assert result==a
    args=run.call_args.args[0]
    assert "--user-agent" in args
    assert args[args.index("--user-agent")+1]==mod.FIREFOX_UA
    assert "--max-time" in args and "--compressed" in args
    assert "playwright" not in str(args)
print("PASS: cheap curl Firefox UA public DDG/Yandex results, no JS or browser session")
print("PASS: HTTP 403/429, cross-host redirects and CAPTCHA stop without retries")
