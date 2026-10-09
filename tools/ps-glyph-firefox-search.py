#!/usr/bin/env python3
"""Read public DuckDuckGo/Yandex result pages with real Playwright Firefox.

Firefox here is Playwright's Firefox build, not a stealth or CAPTCHA bypass.
Navigate as a browser, read visible result links, stop on a bot challenge
or HTTP 403/429, and NEVER persist cookies, page HTML or screenshots.
No login, ads, tracking/captcha interaction, extensions, Tor, proxy tricks,
paid Yandex API or downloading other people's mod archives.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlparse

RESULT_LIMIT = 30
CHALLENGE = re.compile(
    r"captcha|verify (that )?you are (a )?human|unusual traffic|"
    r"automated requests|bot detection|confirm you are not a robot|"
    r"подтвердите.{0,40}(робот|человек)|не робот|"
    r"проверка.{0,40}(робот|браузер)",
    re.IGNORECASE,
)
ENGINE_DOMAINS = {
    "firefox_duckduckgo": ("duckduckgo.com",),
    "firefox_yandex": ("yandex.com", "yandex.ru"),
}


class FirefoxSearchPaused(RuntimeError):
    pass


def engine_url(provider: str, query: str) -> str:
    if provider == "firefox_duckduckgo":
        return "https://duckduckgo.com/?q=" + quote(query)
    if provider == "firefox_yandex":
        return "https://yandex.com/search/?text=" + quote(query)
    raise ValueError("unsupported Firefox search provider")


def matching_engine(host: str, provider: str) -> bool:
    host = (host or "").casefold().strip(".")
    return any(host == domain or host.endswith("." + domain)
               for domain in ENGINE_DOMAINS.get(provider, ()))


def evaluate_page(provider: str, final_url: str, title: str,
                  body: str, links: list[dict], status: int) -> list[tuple[str,str]]:
    """Fail closed on challenges. Accept external links only, later screened
    by the existing title-match and mod-host allowlist."""
    if status in (401, 403, 429, 503):
        raise FirefoxSearchPaused("search engine refused browser request")
    if not matching_engine(urlparse(final_url).hostname or "", provider):
        raise FirefoxSearchPaused("Firefox was redirected away from search engine")
    if CHALLENGE.search(title[:300] + " " + body[:10000]):
        raise FirefoxSearchPaused("human verification or bot challenge displayed")
    if not 200 <= status < 400:
        raise FirefoxSearchPaused("search page HTTP failure")
    output, seen = [], set()
    for raw in links[:1000]:
        if not isinstance(raw, dict):
            continue
        href = str(raw.get("href") or "").strip()
        label = re.sub(r"\s+", " ", str(raw.get("text") or "")).strip()[:240]
        if not href or len(href) > 2048 or len(label) < 4 or href in seen:
            continue
        seen.add(href)
        if matching_engine(urlparse(href).hostname or "", provider):
            # DuckDuckGo wraps targets in /l/?uddg=... ; existing discovery
            # safely unwraps those instead of following redirects blindly.
            if provider != "firefox_duckduckgo" or "/l/?" not in href:
                continue
        output.append((label, href))
        if len(output) == RESULT_LIMIT:
            break
    return output


class FirefoxSearcher:
    """One ephemeral Firefox browser for a small polite, serial batch."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise FirefoxSearchPaused(
                "Playwright missing; install Python package and Firefox browser") from error
        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.firefox.launch(headless=True)
            self.context = self.browser.new_context(
                locale="en-US", viewport={"width": 1280, "height": 900},
                accept_downloads=False)
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None

    def search(self, provider: str, query: str) -> list[tuple[str,str]]:
        if not self.context:
            raise FirefoxSearchPaused("Firefox search context not active")
        page = self.context.new_page()
        try:
            response = page.goto(engine_url(provider, query),
                                 wait_until="domcontentloaded", timeout=25000)
            if not response:
                raise FirefoxSearchPaused("search provider returned no navigation")
            # No click/typing to circumvent access controls. Read the current
            # visible browser result page after ordinary DOM readiness.
            page.wait_for_timeout(900)
            body = page.locator("body").inner_text(timeout=5000)[:10000]
            links = page.locator("a[href]").evaluate_all(
                "(nodes) => nodes.slice(0,1000).map(a => ({href:a.href,text:a.innerText}))")
            return evaluate_page(provider, page.url, page.title(), body,
                                 links, response.status)
        except FirefoxSearchPaused:
            raise
        except Exception as error:
            raise FirefoxSearchPaused(
                "Firefox browser navigation unavailable (no retry/bypass)") from error
        finally:
            page.close()
