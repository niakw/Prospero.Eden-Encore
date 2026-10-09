#!/usr/bin/env python3
"""Build a verified in-game PlayStation graphic mod from local, extracted RomFS.

Use Zacksly's CC BY 3.0 icons as one *shared* source of PlayStation artwork.
Each title still needs identified, hashed game-owned PNG/TGA atlas coordinates.
Never guess which Nintendo A/B/X/Y glyph means Cross/Circle: gameplay,
menus and custom mappings can disagree. Other textures remain untouched.

No online download, native renderer hooks, game dumps or SDK needed.
Output follows ps-glyph-pack.py schema 2 and is installed separately.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError as error:
    raise SystemExit("Requires Pillow locally: python -m pip install Pillow") from error

ROOT_MARKER = "PS5 Button Icons and Controls/"
VARIANTS = {
    "outline-white": "Buttons Outline/White/128w/",
    "outline-black": "Buttons Outline/Black/128w/",
    "solid-white": "Buttons Solid/White/128w/",
    "solid-black": "Buttons Solid/Black/128w/",
    "full-white": "Buttons Full Solid/White/128w/",
    "full-black": "Buttons Full Solid/Black/128w/",
}
ICONS = {
    "cross": "Cross", "circle": "Circle", "square": "Square",
    "triangle": "Triangle", "l1": "L1", "r1": "R1", "l2": "L2",
    "r2": "R2", "l3": "Left Stick Click", "r3": "Right Stick Click",
    "dpad": "D-Pad", "up": "D-Pad Up", "down": "D-Pad Down",
    "left": "D-Pad Left", "right": "D-Pad Right",
    "left_stick": "Left Stick", "right_stick": "Right Stick",
    "options": "Options", "create": "Create", "touchpad": "Touch Pad Press",
    "home": "Home",
}
HEX16 = re.compile(r"[0-9a-fA-F]{16}\Z")
SHA = re.compile(r"[0-9a-fA-F]{64}\Z")
VERSION = re.compile(r"[a-zA-Z0-9_.+ -]{1,64}\Z")
MAX_SPEC = 128 * 1024
MAX_ICON_BYTES = 2 * 1024 * 1024
MAX_ATLAS_BYTES = 128 * 1024 * 1024
MAX_PACK_BYTES = 512 * 1024 * 1024
MAX_ATLASES = 64
MAX_SLOTS = 512
MAX_PIXELS = 25_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidAtlas(ValueError):
    pass


def require(valid: bool, reason: str) -> None:
    if not valid:
        raise InvalidAtlas(reason)


def nondup(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, val in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = val
    return result


def safe_path(value: object) -> Path:
    require(isinstance(value, str) and 0 < len(value) <= 240,
            "invalid game atlas path")
    require("\\" not in value and ":" not in value and not value.startswith("/"),
            "game paths must be relative POSIX paths")
    segments = PurePosixPath(value).parts
    require(bool(segments) and all(s not in ("", ".", "..") and not s.startswith(".")
                                    for s in segments) and "/".join(segments) == value,
            "unsafe or non-normalized path")
    return Path(*segments)


def regular(root: Path, relative: Path) -> Path:
    require(root.is_dir() and not root.is_symlink(), "RomFS root must be a real directory")
    p = root
    for name in relative.parts:
        p = p / name
        require(not p.is_symlink(), "symlink not allowed in source path")
    require(p.is_file(), f"missing original game atlas: {relative.as_posix()}")
    require(p.stat().st_size <= MAX_ATLAS_BYTES, "source atlas too large")
    return p


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_icon(z: zipfile.ZipFile, variant: str, icon: str) -> Image.Image:
    require(variant in VARIANTS, f"unknown icon style: {variant}")
    require(icon in ICONS, f"unknown PlayStation button: {icon}")
    name = ROOT_MARKER + VARIANTS[variant] + ICONS[icon] + ".png"
    try:
        info = z.getinfo(name)
    except KeyError as error:
        raise InvalidAtlas(f"licensed PS5 icon missing in ZIP: {name}") from error
    require(info.file_size <= MAX_ICON_BYTES, "icon has excessive decoded file size")
    with z.open(info) as stream:
        buf = stream.read(MAX_ICON_BYTES + 1)
    require(len(buf) <= MAX_ICON_BYTES, "icon read exceeded limit")
    with Image.open(io.BytesIO(buf)) as original:
        require(original.width <= 1024 and original.height <= 1024,
                "icon dimensions too large")
        image = original.convert("RGBA")
        image.load()
    return image


def rectangle(value: object, width: int, height: int) -> tuple[int, int, int, int]:
    require(isinstance(value, list) and len(value) == 4 and
            all(type(n) is int for n in value), "rect must be [x,y,w,h] integers")
    x, y, w, h = value
    require(x >= 0 and y >= 0 and 0 < w <= 1024 and 0 < h <= 1024 and
            x + w <= width and y + h <= height, "button slot outside source atlas")
    return x, y, w, h


def overlaps(a: tuple[int, int, int, int],
             b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def render(spec: Path, original_root: Path, icons_zip: Path, output: Path) -> Path:
    require(spec.is_file() and not spec.is_symlink() and
            spec.stat().st_size <= MAX_SPEC, "invalid/oversized specification")
    data = json.loads(spec.read_text("utf-8"), object_pairs_hook=nondup)
    require(isinstance(data, dict) and set(data) ==
            {"schema", "title_id", "update_version", "variant", "atlases"},
            "wrong input schema: expected schema/title_id/update_version/variant/atlases")
    require(type(data["schema"]) is int and data["schema"] == 1, "unknown schema version")
    title = data["title_id"]
    version = data["update_version"]
    variant = data["variant"]
    require(isinstance(title, str) and HEX16.fullmatch(title) is not None and
            int(title, 16) != 0, "invalid title ID")
    require(isinstance(version, str) and VERSION.fullmatch(version) is not None,
            "invalid title update version")
    require(variant in VARIANTS, "unsupported button icon style")
    atlases = data["atlases"]
    require(isinstance(atlases, list) and 0 < len(atlases) <= MAX_ATLASES,
            "one to 64 source atlas entries required")
    require(not output.exists() and output.parent.is_dir() and
            not output.parent.is_symlink(), "destination must not yet exist")
    require(icons_zip.is_file() and not icons_zip.is_symlink(), "licensed ZIP not found")

    stage = Path(tempfile.mkdtemp(prefix=".eden-glyph-atlas-", dir=output.parent))
    total = 0
    entries = []
    used = set()
    try:
        with zipfile.ZipFile(icons_zip) as zipped:
            for item in atlases:
                require(isinstance(item, dict) and set(item) ==
                        {"romfs_path", "original_sha256", "slots"},
                        "invalid source atlas record")
                relative = safe_path(item["romfs_path"])
                require(relative.suffix.lower() in (".png", ".tga"),
                        "unsupported game texture format (BNTX/DDS require a verified converter)")
                key = relative.as_posix().casefold()
                require(key not in used, "duplicate case-folding game atlas path")
                used.add(key)
                original = regular(original_root, relative)
                expected = item["original_sha256"]
                require(isinstance(expected, str) and SHA.fullmatch(expected) is not None,
                        "each original atlas needs an exact SHA-256 fingerprint")
                require(digest(original) == expected.lower(),
                        f"wrong game/update atlas fingerprint: {relative}")
                with Image.open(original) as image:
                    require(image.mode == "RGBA" and image.width * image.height <= MAX_PIXELS,
                            "only lossless RGBA game atlases supported; no palettes/swizzle")
                    base = image.copy()
                buttons = item["slots"]
                require(isinstance(buttons, list) and 0 < len(buttons) <= MAX_SLOTS,
                        "atlas must contain 1-512 explicit glyph slots")
                rects = []
                for slot in buttons:
                    require(isinstance(slot, dict) and set(slot) == {"button", "rect"},
                            "each slot requires explicit PlayStation button and rectangle")
                    button = slot["button"]
                    require(button in ICONS, "unsupported PlayStation button name")
                    x, y, w, h = rectangle(slot["rect"], base.width, base.height)
                    box = (x, y, w, h)
                    require(not any(overlaps(box, prev) for prev in rects),
                            "overlapping glyph rectangles rejected")
                    rects.append(box)
                    # Do not guess that a game uses transparent artwork: if
                    # not, clearing this rectangle could destroy a background.
                    sample = base.crop((x, y, x + w, y + h))
                    require(any(a == 0 for a in sample.getchannel("A").getdata()),
                            "slot has no transparency; unsafe to clear/repaint")
                    icon = read_icon(zipped, variant, button)
                    contained = ImageOps.contain(icon, (w, h), Image.Resampling.LANCZOS)
                    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    tile.alpha_composite(contained,
                                         ((w - contained.width) // 2,
                                          (h - contained.height) // 2))
                    # Explicitly replace the *whole* isolated sprite rect;
                    # visual meaning is declared by the game owner in spec.
                    base.paste(tile, (x, y))
                target = stage / "replacement" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                base.save(target, format="PNG" if relative.suffix.lower() == ".png" else "TGA")
                with Image.open(target) as encoded:
                    require(encoded.mode == "RGBA" and encoded.size == base.size,
                            "output game atlas layout changed unexpectedly")
                total += target.stat().st_size
                require(total <= MAX_PACK_BYTES, "generated graphics exceed 512 MiB")
                entries.append({
                    "romfs_path": relative.as_posix(),
                    "replacement": (Path("replacement") / relative).as_posix(),
                    "original_sha256": expected.lower(),
                    "replacement_sha256": digest(target),
                })
        manifest = {
            "schema": 2, "title_id": title.upper(), "update_version": version,
            "rights": "Zacksly PS5 Button Icons and Controls CC BY 3.0; edited for local game atlas",
            "files": entries,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", "utf-8")
        (stage / "ARTWORK_ATTRIBUTION.txt").write_text(
            "PlayStation button artwork: PS5 Button Icons and Controls by Zacksly\n"
            "Source: https://zacksly.itch.io\n"
            "License: https://creativecommons.org/licenses/by/3.0/ (CC BY 3.0)\n"
            "Modified: icons resized and composited into locally sourced game atlases.\n"
            "This pack contains modified game-owned texture data: for local use only,\n"
            "unless you separately hold redistribution rights for that game artwork.\n",
            "utf-8")
        stage.rename(output)
        return output
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def discover(root: Path, limit: int = 200) -> list[dict]:
    require(root.is_dir() and not root.is_symlink(), "RomFS root invalid")
    found = []
    suffixes = {".png", ".tga", ".bntx", ".dds", ".szs", ".bfres", ".nxtx"}
    hints = ("ui", "button", "control", "hud", "prompt", "icon", "input", "gamepad")
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        for name in sorted(files):
            source = Path(directory) / name
            if source.is_symlink() or source.suffix.lower() not in suffixes:
                continue
            rel = source.relative_to(root).as_posix()
            if not any(word in rel.lower() for word in hints):
                continue
            found.append({"romfs_path": rel,
                          "kind": "RGBA image candidate" if source.suffix.lower() in (".png", ".tga")
                          else "PROPRIETARY: decoder/encoder required"})
            if len(found) >= limit:
                return found
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discover", "render"))
    parser.add_argument("--original-romfs", type=Path, required=True)
    parser.add_argument("--icons-zip", type=Path, help="original licensed Zacksly ZIP (render)")
    parser.add_argument("--spec", type=Path, help="JSON coordinates, title ID/version and source SHA (render)")
    parser.add_argument("--out", type=Path, help="new output pack folder (render)")
    args = parser.parse_args()
    try:
        if args.action == "discover":
            print(json.dumps({"candidates": discover(args.original_romfs)}, indent=2))
        else:
            require(args.icons_zip is not None and args.spec is not None and
                    args.out is not None, "render requires --icons-zip --spec --out")
            target = render(args.spec, args.original_romfs, args.icons_zip, args.out)
            print(f"GENERATED {target}; verify/install with tools/ps-glyph-pack.py")
        return 0
    except (InvalidAtlas, OSError, ValueError, zipfile.BadZipFile,
            Image.DecompressionBombError, UnidentifiedImageError) as e:
        print(f"REJECTED in-game glyph atlas: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
