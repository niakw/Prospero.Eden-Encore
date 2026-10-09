#!/usr/bin/env python3
"""Public DDG/Yandex mod search with curl using a Firefox HTTP User-Agent.

Using Firefox's User-Agent in curl is NOT a real Firefox browser: JavaScript,
browser cookies and browser rendering are absent. This cheap route is used
first; use ps-glyph-firefox-search.py ONLY for normal page rendering when
curl cannot show results. Never bypass CAPTCHAs/access/rate restrictions.
No headless-browser stealth, login, proxies, mod downloads or raw HTML logs.
"""
from __future__ import annotations
from html.parser import HTMLParser
import re
import subprocess
from urllib.parse import quote, urljoin, urlparse

FIREFOX_UA=("Mozilla/5.0 (X11; Linux x86_64; rv:140.0) "
            "Gecko/20100101 Firefox/140.0")
CHALLENGE=re.compile(
    r"captcha|anomaly-modal|verify.{0,30}human|unusual traffic|"
    r"automated requests|bot detection|are you a robot|"
    r"не робот|проверка.{0,40}(робот|браузер)",
    re.IGNORECASE)
METADATA_MARKER=b"\nEDEN_SEARCH_HTTP:"
MAX_BODY=2*1024*1024
MAX_SEARCH_RESULTS=30

class CurlSearchPaused(RuntimeError):
    pass

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]
        self.current=None
        self.depth=0
    def handle_starttag(self,tag,attrs):
        if tag!="a":return
        attributes=dict(attrs)
        href=attributes.get("href","")
        if self.current is None and href:
            self.current=[href,[]]
            self.depth=1
        elif self.current:
            self.depth+=1
    def handle_data(self,data):
        if self.current:self.current[1].append(data)
    def handle_endtag(self,tag):
        if tag!="a" or self.current is None:return
        self.depth-=1
        if self.depth<=0:
            href,parts=self.current
            label=re.sub(r"\s+"," "," ".join(parts)).strip()[:260]
            if href and label:self.links.append((label,href))
            self.current=None

def engine_url(provider,query):
    if provider=="curl_duckduckgo":
        return "https://html.duckduckgo.com/html/?q="+quote(query)
    if provider=="curl_yandex":
        return "https://yandex.com/search/?text="+quote(query)
    raise ValueError("unknown public curl provider")

def engine_matches(provider,url):
    host=(urlparse(url).hostname or "").casefold()
    names=("duckduckgo.com",) if provider=="curl_duckduckgo" else (
        "yandex.com","yandex.ru")
    return any(host==name or host.endswith("."+name) for name in names)

def parse_page(provider,original_url,final_url,status,body):
    if not 200<=status<400:
        raise CurlSearchPaused("search engine returned HTTP "+str(status))
    if not engine_matches(provider,final_url):
        raise CurlSearchPaused("search redirected to another origin")
    text=body.decode("utf-8","replace")
    # No automatic attempt to solve any human verification.
    if CHALLENGE.search(text[:80000]):
        raise CurlSearchPaused("search page displays a CAPTCHA or verification")
    p=LinkParser()
    p.feed(text[:MAX_BODY])
    result,seen=[],set()
    for label,href in p.links[:2500]:
        link=urljoin(final_url,href)
        if engine_matches(provider,link) and "/l/?" not in link:
            continue
        if link not in seen and len(link)<2048:
            seen.add(link)
            result.append((label,link))
        if len(result)>=MAX_SEARCH_RESULTS:break
    return result

def search(provider,query):
    url=engine_url(provider,query)
    cmd=["curl","--silent","--show-error","--location",
         "--max-redirs","2","--max-time","23","--connect-timeout","9",
         "--compressed","--user-agent",FIREFOX_UA,
         "--write-out","\nEDEN_SEARCH_HTTP:%{http_code}\nEDEN_SEARCH_URL:%{url_effective}\n",
         url]
    try:
        run=subprocess.run(cmd,capture_output=True,timeout=28,check=False)
    except (OSError,subprocess.TimeoutExpired) as error:
        raise CurlSearchPaused("curl unavailable or timed out") from error
    if run.returncode!=0:
        raise CurlSearchPaused("curl public search request refused/unavailable")
    body,sep,trailer=run.stdout.rpartition(METADATA_MARKER)
    if not sep or len(body)>MAX_BODY:
        raise CurlSearchPaused("invalid/oversized public search response")
    status_line,sep,url_line=trailer.partition(b"\nEDEN_SEARCH_URL:")
    if not sep:
        raise CurlSearchPaused("missing final engine URL")
    try:
        status=int(status_line.decode("ascii").strip())
    except (ValueError,UnicodeDecodeError) as error:
        raise CurlSearchPaused("bad HTTP status") from error
    destination=url_line.decode("utf-8","replace").strip()
    return parse_page(provider,url,destination,status,body)
