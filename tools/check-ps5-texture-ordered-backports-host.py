#!/usr/bin/env python3
"""F03/F04: verify exact ordered PS5 texture-view shipping patch stack.

Reverse four PS5 view/remap patches from shipping, confirm the reviewed
pre-F04 source, and replay with Git to reproduce exact shipping bytes.
Also verify source/receipt SHA-256 contracts. Not a full console build.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REL = Path("src/video_core/texture_cache/texture_cache.h")
ACTIVE = ROOT / "vendor/encore-active/eden-backports"
MANIFEST = json.loads((ACTIVE / "manifest.json").read_text())
SOURCE = ACTIVE / REL
BYTES = SOURCE.read_bytes()

def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

owner = MANIFEST["entries"][REL.as_posix()]
assert owner["active"] == sha256(BYTES), "shipping texture cache digest mismatch"
assert owner["bytes"] == len(BYTES), "shipping texture cache size mismatch"

PATCH_NAMES = (
    "eden-ps5-texture-tic-layer-bounds.patch",
    "eden-ps5-texture-remapped-view-rebind.patch",
    "eden-ps5-texture-remap-target-invalidation.patch",
    "eden-ps5-texture-missing-channel-slot-guard.patch",
)
installer = (ROOT / "tools/apply-eden-backports.sh").read_text()
positions = [
    installer.index(f'apply_one "$root/headless/backports/{name}"')
    for name in PATCH_NAMES
]
assert positions == sorted(positions), "texture patch replay order changed"
patches = [ROOT / "headless/backports" / name for name in PATCH_NAMES]
for file in patches:
    receipt = f".encore-backport-{file.stem.removeprefix('eden-')}.sha256"
    assert MANIFEST["shipping_receipts"].get(receipt) == sha256(file.read_bytes()), (
        "stale texture patch receipt", receipt
    )

PRE_F04_SHA256 = "3c129bb7ecf389d6f95c852ac9afbf1956fcc6e31d19bbeccaef757228af450a"
PRE_F04_BYTES = 117051

def run(stage: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["git", "apply", *args], cwd=stage, text=True,
        capture_output=True, timeout=25,
    )
    assert result.returncode == 0, (args, result.stderr[-3500:])

with tempfile.TemporaryDirectory(prefix="encore-texture-stack-replay-") as td:
    stage = Path(td)
    target = stage / REL
    target.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE, target)

    for patch in reversed(patches):
        run(stage, ["--reverse", "--check", str(patch)])
        run(stage, ["--reverse", str(patch)])
    baseline = target.read_bytes()
    assert len(baseline) == PRE_F04_BYTES, "unexpected pre-F04 texture source size"
    assert sha256(baseline) == PRE_F04_SHA256, "unexpected pre-F04 texture source"
    print("ENCORE_F03_F04_TEXTURE_BASELINE_PASS", len(baseline))

    for patch in patches:
        run(stage, ["--check", str(patch)])
        run(stage, [str(patch)])
    assert target.read_bytes() == BYTES, "four-patch roundtrip changed source"
    print("ENCORE_F03_F04_TEXTURE_PATCH_REPLAY_PASS", len(BYTES), len(patches))
