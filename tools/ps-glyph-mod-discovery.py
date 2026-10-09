#!/usr/bin/env python3
"""Incremental controller-glyph mod discovery across ALL indexed Switch-1 titles.

Accepts multi-region Switch TitleDB-derived full Switch 1 catalog. Supports
DuckDuckGo HTML (public, slow, stop at HTTP 403/429/captcha), GitHub public
repository Search API, and credentialed OFFICIAL Yandex Search API (paid;
disabled without keys). Also exports direct prefilled DDG/Yandex links so
blocked/rate-limited providers can be inspected manually. Results are
source LEADS only, never game-compatible art or license clearance.

Progress is resumable across GitHub Actions runs; batch size/request count
is capped. No mod archives are downloaded, scraped or redistributed, and
no changes to emulator gameplay/graphics are made.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MAX_CATALOG = 250000
MAX_REPORT = 12 * 1024 * 1024
MAX_CANDIDATES_PER_GAME = 20
ALLOWED_SUFFIXES = (
    "gamebanana.com", "nexusmods.com", "moddb.com", "github.com",
    "gbatemp.net", "steamcommunity.com", "thunderstore.io",
    "curseforge.com", "modworkshop.net", "romhacking.net", "gamejolt.com"
)
TERMS = (
    "controller", "glyph", "button", "prompt", "playstation",
    "dualsense", "dualshock", "xbox", "ps4", "ps5", "ui", "layout",
    "buttons", "текстуры", "кнопки", "иконки", "gamepad"
)
PROVIDERS = ("duckduckgo", "github", "yandex")
HTTP_TIMEOUT = 16

class DiscoveryError(ValueError):
    pass

class ProviderPaused(Exception):
    """Stop when a search provider throttles, forbids, or shows a challenge."""

def require(condition, msg):
    if not condition:
        raise DiscoveryError(msg)

def textfold(x):
    return re.sub(r"\W+", " ", str(x).casefold(), flags=re.UNICODE).strip()

def read_json(path: Path, bound: int = MAX_REPORT):
    require(path.is_file() and not path.is_symlink() and
            1 <= path.stat().st_size <= bound, "missing/oversized JSON metadata")
    return json.loads(path.read_text("utf-8"))

def game_query(name: str, variant: int) -> str:
    safe = re.sub(r"[\x00-\x1f\x7f\"<>]", " ", name).strip()
    require(2 <= len(safe) <= 260, "unsafe game title")
    if variant == 0:
        return f'"{safe}" Switch PlayStation PS4 PS5 controller buttons UI mod'
    if variant == 1:
        return f'"{safe}" button prompts DualSense Xbox controller glyphs PC mod'
    if variant == 2:
        return f'"{safe}" UI gamepad icons mod site:gamebanana.com'
    return f'"{safe}" кнопки PlayStation интерфейс мод'

def search_urls(query: str) -> dict:
    return {
        "duckduckgo": "https://duckduckgo.com/?q=" + quote(query),
        "yandex": "https://yandex.com/search/?text=" + quote(query),
        "gamebanana": "https://www.google.com/search?q=" + quote(
            query + " site:gamebanana.com/mods"),
    }

def canonical_link(href: str) -> str | None:
    href = html.unescape(href).strip()
    if href.startswith("//"): href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.lower().endswith("duckduckgo.com") or parsed.path.startswith("/l/"):
        url = parse_qs(parsed.query).get("uddg")
        if url:
            href = url[0]
            parsed = urlparse(href)
    host = (parsed.hostname or "").casefold().strip(".")
    if (parsed.scheme not in ("https", "http") or
        not any(host == suffix or host.endswith("." + suffix)
                for suffix in ALLOWED_SUFFIXES) or
        parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
        return None
    # No URL query tokens/tracking copied into metadata.
    return "https://" + host + parsed.path.rstrip("/")

class DuckResults(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_result = False
        self.href = ""
        self.parts: list[str] = []
        self.found: list[tuple[str,str]] = []
    def handle_starttag(self, tag, attrs):
        if tag != "a": return
        a = dict(attrs)
        if "result__a" in a.get("class", "").split():
            self.in_result = True
            self.href = a.get("href", "")
            self.parts = []
    def handle_data(self, data):
        if self.in_result: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.in_result:
            label = " ".join(self.parts).strip()
            if self.href and label:
                self.found.append((label, self.href))
            self.in_result = False

def request_bytes(url: str, headers: dict | None = None,
                  data: bytes | None = None, cap: int = 2 * 1024 * 1024) -> bytes:
    try:
        with urlopen(Request(url, data=data, headers=headers or {
             "User-Agent": "EdenEncoreModDiscovery/1.0 (read-only search)" }),
                     timeout=HTTP_TIMEOUT) as response:
            blob = response.read(cap + 1)
            require(len(blob) <= cap, "search response exceeded byte budget")
            return blob
    except HTTPError as e:
        if e.code in (401, 403, 429, 503):
            raise ProviderPaused(f"provider unavailable or rate limited (HTTP {e.code})") from e
        raise DiscoveryError(f"search HTTP {e.code}") from e
    except (URLError, OSError) as e:
        raise ProviderPaused("network unavailable") from e

def ddg(query: str) -> list[tuple[str,str]]:
    endpoint = "https://html.duckduckgo.com/html/?q=" + quote(query)
    doc = request_bytes(endpoint).decode("utf-8", "replace")
    if any(t in doc.lower() for t in ("anomaly-modal", "captcha", "bots use duckduckgo")):
        raise ProviderPaused("DuckDuckGo asked for human verification")
    parser = DuckResults()
    parser.feed(doc)
    return parser.found[:20]

def github(query: str) -> list[tuple[str,str]]:
    # GitHub REST searches REPOSITORY NAMES/DESCRIPTIONS, not hidden code,
    # ZIPs, executable mods or private repositories.
    words = [x for x in re.split(r"\W+", query) if len(x) > 2]
    q = " ".join(words[:9]) + " in:name,description"
    endpoint = ("https://api.github.com/search/repositories?q=" + quote(q) +
                "&per_page=10")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "EdenEncore-Mod-Discovery"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token: headers["Authorization"] = "Bearer " + token
    result = json.loads(request_bytes(endpoint, headers=headers))
    return [(x.get("full_name", ""), x.get("html_url", ""))
            for x in result.get("items", [])[:10] if isinstance(x, dict)]

def yandex(query: str) -> list[tuple[str,str]]:
    token = os.getenv("YANDEX_SEARCH_API_KEY", "").strip()
    folder = os.getenv("YANDEX_SEARCH_FOLDER_ID", "").strip()
    require(bool(token and folder), "Yandex official API needs key and folder ID")
    body = json.dumps({
        "query": {"searchType": "SEARCH_TYPE_COM", "queryText": query[:400],
                  "familyMode": "FAMILY_MODE_MODERATE", "page": "0"},
        "folderId": folder, "responseFormat": "FORMAT_XML",
        "l10n": "LOCALIZATION_EN",
        "groupSpec": {"groupMode": "GROUP_MODE_FLAT", "groupsOnPage": "10",
                      "docsInGroup": "1"},
    }).encode()
    data = request_bytes("https://searchapi.api.cloud.yandex.net/v2/web/search",
                         {"Api-Key": token, "Content-Type": "application/json",
                          "User-Agent": "EdenEncore-Mod-Discovery"}, body)
    response = json.loads(data)
    raw = base64.b64decode(response["rawData"], validate=True)
    require(len(raw) < 2 * 1024 * 1024, "Yandex XML exceeds bound")
    tree = ET.fromstring(raw)
    return [(node.findtext("title") or "", node.findtext("url") or "")
            for node in tree.findall(".//doc")][:20]

def label_candidate(title: str, query: str, label: str, uri: str, provider: str) -> dict | None:
    clean_url = canonical_link(uri)
    if not clean_url: return None
    words = set(textfold(title).split())
    words = {x for x in words if len(x) >= 3 and x not in
             ("the","and","for","edition","nintendo","switch","complete","game")}
    result_words = set(textfold(label + " " + urlparse(clean_url).path).split())
    matches = len(words & result_words)
    if words and matches < min(2, len(words)): return None
    haystack = textfold(label + " " + uri)
    modwords = [term for term in TERMS if term in haystack]
    if not modwords: return None
    return {"url": clean_url, "page_title": label[:240],
            "provider": provider, "keyword_matches": sorted(modwords[:12]),
            "source_platform": "unknown_or_multiplatform",
            "same_game_name_match": True,
            "verified_file_exists": False, "original_switch_asset_verified": False,
            "ps5_glyphs_compatible": False, "safety": "UNVERIFIED_SOURCE_LEAD"}

def candidates_for(title: str, query: str, results: list[tuple[str,str]],
                   provider: str) -> list[dict]:
    output, seen = [], set()
    for label, url in results:
        candidate = label_candidate(title, query, label, url, provider)
        if not candidate or candidate["url"].casefold() in seen: continue
        output.append(candidate)
        seen.add(candidate["url"].casefold())
        if len(output) >= MAX_CANDIDATES_PER_GAME: break
    return output

def discover(catalog: dict, state: dict, limit: int,
             provider: str = "none", network: bool = False,
             variant: int = 0, interval: float = 2.) -> tuple[dict,dict]:
    require(catalog.get("schema") == 1 and isinstance(catalog.get("games"), list) and
            0 < len(catalog["games"]) <= MAX_CATALOG, "invalid Switch1 catalog")
    games = catalog["games"]
    fingerprint = hashlib.sha256(json.dumps(games, sort_keys=True,
                                             ensure_ascii=False).encode()).hexdigest()
    if state:
        require(state.get("schema") == 1 and state.get("catalog_sha256") == fingerprint,
                "catalog changed: explicit rescan/state migration required")
    offset = state.get("next_offset", 0)
    require(type(offset) is int and 0 <= offset <= len(games), "bad resume offset")
    require(type(limit) is int and 1 <= limit <= 250, "batch must contain 1-250 games")
    require(provider in PROVIDERS + ("none",), "unknown discovery provider")
    require(variant in (0,1,2,3), "unsupported query variant")
    if network:
        require(provider in PROVIDERS, "network mode requires explicit provider")
    todo = games[offset:min(len(games),offset+limit)]
    rows, errors = [], []
    cursor = offset
    for game in todo:
        title = game["title"]
        tid = game["title_id"]
        require(isinstance(title, str) and isinstance(tid, str) and
                len(title) < 320 and re.fullmatch(r"0100[0-9A-Fa-f]{9}000", tid),
                "invalid Switch-1 TitleDB record")
        # Cycle across distinct semantic/glyph queries on later sweeps;
        # don't burn search-engine rate budgets on dozens of sites per title.
        query = game_query(title, variant)
        urls = search_urls(query)
        discovered = []
        status = "query_prepared_not_executed"
        if network:
            try:
                found = {"duckduckgo": ddg, "github": github, "yandex": yandex}[provider](query)
                discovered = candidates_for(title, query, found, provider)
                status = "searched_links_found" if discovered else "searched_no_matching_links"
            except ProviderPaused as exc:
                errors.append({"game_title": title, "provider": provider,
                               "reason": str(exc)})
                # Never mark the rate-limited title as fully processed.
                break
            except (DiscoveryError, ValueError, ET.ParseError, KeyError,
                    TypeError, json.JSONDecodeError) as exc:
                errors.append({"game_title": title, "provider": provider,
                               "reason": str(exc)[:180]})
                break
        rows.append({"title_id": tid, "game": title,
                     "query": query, "search_links": urls,
                     "discovery_status": status, "leads": discovered,
                     "mod_pack_ready": False, "title_update_romfs_verified": False})
        cursor += 1
        if network and interval > 0 and cursor < offset + len(todo):
            time.sleep(interval)
    new_state = {"schema": 1, "catalog_sha256": fingerprint,
                 "next_offset": cursor, "catalog_total": len(games),
                 "search_variant": variant, "last_provider": provider,
                 "completed_catalog_scan": cursor == len(games)}
    report = {"schema": 1, "catalog_total": len(games),
              "batch_offset": offset, "next_offset": cursor,
              "provider": provider, "network_queries_enabled": network,
              "source_leads": sum(len(r["leads"]) for r in rows),
              "games_examined": len(rows), "games": rows, "errors": errors,
              "mod_asset_downloads": 0, "gameplay_glyphs_autoenabled": 0,
              "status_note": ("Search leads only. Game title/platform matches, licenses, "
                              "archive bytes, per-version ROMFS and scene mappings "
                              "remain subject to independently verified input.") }
    return report, new_state

def new_file(path: Path, data: dict):
    require(path.parent.is_dir() and not path.parent.is_symlink() and
            not path.exists() and not path.is_symlink(), "must write to a new file")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", required=True, type=Path)
    p.add_argument("--state-in", type=Path)
    p.add_argument("--state-out", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--max-games", type=int, default=20)
    p.add_argument("--provider", choices=("none", *PROVIDERS), default="none")
    p.add_argument("--network", action="store_true",
                   help="explicit opt-in to real search requests")
    p.add_argument("--query-variant", type=int, default=0)
    p.add_argument("--interval", type=float, default=2.)
    args = p.parse_args()
    try:
        require(0 <= args.interval <= 30, "invalid polite search interval")
        catalog = read_json(args.catalog, 128*1024*1024)
        state = read_json(args.state_in) if args.state_in and args.state_in.exists() else {}
        report, progress = discover(catalog, state, args.max_games,
                                    args.provider, args.network,
                                    args.query_variant, args.interval)
        new_file(args.report, report)
        new_file(args.state_out, progress)
        print("GLYPH MOD SEARCH:", report["games_examined"], "Switch1 titles,",
              report["source_leads"], "source leads,",
              len(report["errors"]), "provider errors; cursor", progress["next_offset"],
              "/", progress["catalog_total"], "(never autoenable)")
        return 1 if report["errors"] else 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print("DISCOVERY BLOCKED:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
