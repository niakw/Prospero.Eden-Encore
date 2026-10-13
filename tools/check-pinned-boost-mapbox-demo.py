#!/usr/bin/env python3
"""R423: classify third-party Mapbox public demo tokens without modifying pinned Boost.

The GitHub secret-scanning alert is NOT a credential belonging to Eden Encore.
A vendor test must never print the token or make network requests to validate it.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "vendor/sources/eden-cpm/boost/boost-1.90.0/libs/math/doc"
APPROVED = (
    "html/math_toolkit/hypergeometric/hypergeometric_1f1.html",
    "graphs/hypergeometric_1f1/positive_abz.html",
    "graphs/hypergeometric_1f1/negative_b_incalculable.html",
    "graphs/hypergeometric_1f1/negative_b.html",
    "graphs/hypergeometric_1f1/negative_ab.html",
    "graphs/hypergeometric_1f1/negative_a.html",
)
KEY = re.compile(r"""["']?mapboxAccessToken["']?\s*:\s*["']([A-Za-z0-9._-]+)["']""")
unique_tokens = set()
total = 0
for relative in APPROVED:
    file = BASE / relative
    assert file.is_file(), f"Missing pinned Boost HTML fixture: {relative}"
    contents = file.read_text(encoding="utf-8-sig")
    matches = KEY.findall(contents)
    assert matches and len(matches) == contents.count("mapboxAccessToken"), (
        f"Unexpected Mapbox token format in pinned Boost HTML: {relative}")
    for token in matches:
        assert token.startswith("pk."), "Unexpected PRIVATE or unknown Mapbox token in vendored HTML"
        assert token.count(".") == 2, "Invalid Mapbox token type"
        unique_tokens.add(token)
    total += len(matches)
# Public Plotly demo credential is repeated in five embedded graphs in the
# generated hypergeometric document and once in each of five graph snippets.
assert total == 10 and len(unique_tokens) == 1, "Upstream Mapbox demo provenance changed"
public_token = next(iter(unique_tokens))
encoded_account = public_token.split(".")[1]
account = json.loads(base64.urlsafe_b64decode(
    encoded_account + "=" * (-len(encoded_account) % 4)))
assert account.get("u") == "chriddyp", "Expected upstream Plotly publisher identity"
# Guard first-party build scripts and GitHub workflows: demo keys must never be
# substituted with user-controlled secrets or uploaded as release credentials.
for folder in (ROOT / ".github/workflows",):
    for file in folder.glob("*.yml"):
        data = file.read_text()
        assert "MAPBOX_TOKEN" not in data, "Mapbox credential wired into CI"
        assert "mapboxAccessToken" not in data, "Embedded Mapbox demo leaked into CI"
package = (ROOT / "tools/package-headless-native.sh").read_text()
# The packaging pipeline copies the app, native modules, UI and legal notices;
# do not ever ship the vendored Boost documentation or its public demo token.
assert "vendor/sources" not in package and "mapboxAccessToken" not in package
assert "MAPBOX_TOKEN" not in package
print("R423: PASS — ten public Plotly Mapbox demo occurrences in six pinned Boost HTML files")
print("R423: PASS — no CI Mapbox token injection; preserved Boost reproducibility")
