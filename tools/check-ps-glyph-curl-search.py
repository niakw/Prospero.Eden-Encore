#!/usr/bin/env python3
"""No-network tests: curl Firefox UA, DDG/Yandex links and refusal policy."""
import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location(
    "eden_curl_search_test",Path(__file__).with_name("ps-glyph-curl-search.py"))
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert "Firefox/" in mod.FIREFOX_UA
ddg_url = urlsplit(mod.engine_url("curl_duckduckgo", "BOTW PS4"))
yandex_url = urlsplit(mod.engine_url("curl_yandex", "BOTW кнопки"))
assert (ddg_url.scheme, ddg_url.hostname, ddg_url.path) == (
    "https", "html.duckduckgo.com", "/html/")
assert parse_qs(ddg_url.query)["q"] == ["BOTW PS4"]
assert (yandex_url.scheme, yandex_url.hostname, yandex_url.path) == (
    "https", "yandex.com", "/search/")
assert parse_qs(yandex_url.query)["text"] == ["BOTW кнопки"]
html=b'<html><body><a class="result__a" href="/l/?uddg=https%3A%2F%2Fgamebanana.com%2Fmods%2F659253">Zelda BOTW DS4 mod</a><a href="https://github.com/test/botw-controller-buttons">BOTW controller glyphs</a></body></html>'
a=mod.parse_page("curl_duckduckgo","https://html.duckduckgo.com/html/?q=BOTW",
                 "https://html.duckduckgo.com/html/?q=BOTW",200,html)
assert len(a)==2
first=urlsplit(a[0][1])
assert (first.scheme,first.hostname,first.path,first.username,first.password) == (
    "https","html.duckduckgo.com","/l/",None,None)
assert parse_qs(urlsplit(a[0][1]).query).get("uddg") == ["https://gamebanana.com/mods/659253"]
b=mod.parse_page("curl_yandex","https://yandex.com/search/?text=BOTW",
                 "https://yandex.com/search/?text=BOTW",200,html)
# A DDG-relative /l/ URL must NOT be treated as a valid Yandex result.
assert b == [("BOTW controller glyphs",
              "https://github.com/test/botw-controller-buttons")]
for status,body,where in [
    (403,html,"https://html.duckduckgo.com/html/"),
    (429,html,"https://html.duckduckgo.com/html/"),
    (200,b"CAPTCHA. Verify you are human","https://html.duckduckgo.com/html/"),
    (200,html,"https://evil.invalid/login"),
    (200,html,"https://html.duckduckgo.com.evil.invalid/html/"),
    (200,html,"https://html.duckduckgo.com@evil.invalid/html/"),
    (200,html,"http://html.duckduckgo.com/html/"),
    (302,html,"https://html.duckduckgo.com/html/")
]:
    try:mod.parse_page("curl_duckduckgo","https://html.duckduckgo.com/",
                       where,status,body)
    except mod.CurlSearchPaused:pass
    else:raise AssertionError("illegal source accepted")
# Do not accept protocol escapes, credentials, host suffix tricks or a DDG
# URL that only *contains* "/l/?" in its query rather than its real path.
for hostile in (
    "javascript:alert(1)", "data:text/html,payload",
    "https://user@evil.invalid/path", "http://mod.example/item",
    "https://html.duckduckgo.com/search/?next=/l/?uddg=x",
):
    injected=(f'<a href="{hostile}">Injected result</a>').encode()
    rows=mod.parse_page("curl_duckduckgo",
        "https://html.duckduckgo.com/html/","https://html.duckduckgo.com/html/",
        200,injected)
    assert not rows, hostile
for hostile_url in (
    "https://html.duckduckgo.com.evil.invalid/html/",
    "https://html.duckduckgo.com@evil.invalid/html/",
    "http://html.duckduckgo.com/html/",
    "https://html.duckduckgo.com:444/html/",
):
    assert not mod.engine_matches("curl_duckduckgo",hostile_url),hostile_url
marker=b"\nEDEN_SEARCH_HTTP:200\nEDEN_SEARCH_URL:https://html.duckduckgo.com/html/?q=BOTW\n"
with patch.object(mod.subprocess,"run",
                  return_value=SimpleNamespace(returncode=0,stdout=html+marker,stderr=b"")) as run:
    result=mod.search("curl_duckduckgo","BOTW")
    assert result==a
    args=run.call_args.args[0]
    assert "--user-agent" in args
    assert args[args.index("--user-agent")+1]==mod.FIREFOX_UA
    assert "--max-time" in args and "--compressed" in args
    assert "--location" not in args and "--max-redirs" not in args
    assert args[args.index("--proto")+1]=="=https"
    assert "playwright" not in str(args)
print("PASS: cheap curl Firefox UA public DDG/Yandex results, no JS or browser session")
print("PASS: HTTP 403/429, cross-host redirects and CAPTCHA stop without retries")
