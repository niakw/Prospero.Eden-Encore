#!/usr/bin/env python3
"""Fetch existing physical retail scans for a host-only OpenGL visual fixture.

Not bundled with the emulator or committed to the repository. All screenshots
are rendered by the real launcher C++/GL pipeline, never an image generator.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
from pathlib import Path
import urllib.request

from PIL import Image

BASE = "https://images.launchbox-app.com/"
# Verified against a Switch title's Box - Front (Europe), Box - Back
# (France) and existing game background image (LaunchBox id 79189).
MEDIA = {
    "botw-front.tga": "a8bcb4cc-a3b0-4cf0-82f3-cb10dd18b27c.jpg",
    "botw-back.tga": "b5f2899a-717f-4544-b63f-ee5d13e24483.jpg",
    "botw-hero.tga": "9ec55095-ae9a-4da6-b1a4-025dfe92ca4b.jpg",
}


def download(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    receipts = []
    for filename, source in MEDIA.items():
        url = BASE + source
        request = urllib.request.Request(
            url, headers={"User-Agent": "EdenEncore-OpenGL-VisualCheck/1.0"})
        with urllib.request.urlopen(request, timeout=35) as response:
            body = response.read(12 * 1024 * 1024 + 1)
        if len(body) > 12 * 1024 * 1024:
            raise ValueError(f"Image exceeds test fixture limit: {source}")
        with Image.open(BytesIO(body)) as image:
            image.load()
            if image.width < 350 or image.height < 350:
                raise ValueError(f"Image too small: {source} {image.size}")
            if image.width * image.height > 12_000_000:
                raise ValueError(f"Image too large: {source} {image.size}")
            image = image.convert("RGB")
            # Native code renders at <=1920x1080. Avoid shipping enormous TGAs.
            image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            image.save(destination / filename, format="TGA")
        receipts.append(
            f"{filename}\t{url}\tsha256:{hashlib.sha256(body).hexdigest()}\n")
    (destination / "source-receipts.txt").write_text("".join(receipts))
    print("HOST_RETAIL_SCANS: fetched 2 physical faces and 1 game background")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("directory", type=Path)
    args = cli.parse_args()
    download(args.directory)
