#!/usr/bin/env python3
"""Replay the EXACT pinned Eden guest-memory patches against the real upstream TU.

Runs on GitHub Actions only. Downloads only the 42-kB public, pinned and
SHA-1-verified upstream src/core/memory.cpp, then applies the same ordered
guest patches as tools/apply-eden-backports.sh. No PS5 SDK, emulator build,
hardware, writable user device, or external unpinned source is required.
"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
apply_source = (root / "tools/apply-eden-backports.sh").read_text()
pin = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
blob_sha = "837016de1d4efe74d2efb8df0d9de10aa10d8a26"
url = ("https://raw.githubusercontent.com/eden-emulator/mirror/"
       + pin + "/src/core/memory.cpp")
assert f"expected={pin}" in apply_source, "Production upstream pin drifted"
patch_names = (
    "eden-ps5-guest-mapping-diagnostics.patch",
    "eden-ps5-guest-walk.patch",
    "eden-ps5-guest-zero-alias.patch",
    "eden-ps5-guest-map-null-backing.patch",
    "eden-ps5-guest-span.patch",
)
pos = [apply_source.index(f'apply_one "$root/headless/backports/{name}"')
       for name in patch_names]
assert pos == sorted(pos), "Backport ordering does not preserve valid alias handling"

last_error = None
for attempt in range(3):
    try:
        req = Request(url, headers={"User-Agent": "Eden-Encore-pinned-source-CI"})
        with urlopen(req, timeout=18) as reply:
            if reply.status != 200:
                raise RuntimeError(f"Public upstream HTTP status {reply.status}")
            upstream = reply.read(1024 * 1024 + 1)
            if len(upstream) > 1024 * 1024:
                raise RuntimeError("Upstream TU is too large: refuse unpinned content")
        break
    except (URLError, HTTPError, TimeoutError, OSError) as exc:
        last_error = exc
        if attempt < 2:
            time.sleep(1)
else:
    raise SystemExit(f"Could not verify pinned upstream bytes: {last_error}")
actual_sha = hashlib.sha1(
    b"blob " + str(len(upstream)).encode("ascii") + b"\0" + upstream
).hexdigest()
assert actual_sha == blob_sha, (
    f"Pinned upstream content drift: {actual_sha} != {blob_sha}"
)
original = upstream.decode("utf-8")

with tempfile.TemporaryDirectory(prefix="eden-pinned-guest-replay-") as work:
    base = Path(work)
    path = base / "src/core/memory.cpp"
    path.parent.mkdir(parents=True)
    path.write_bytes(upstream)
    for name in patch_names:
        patch = root / "headless/backports" / name
        subprocess.run(
            ["git", "apply", "--check", str(patch)],
            cwd=base, check=True, timeout=20,
        )
        subprocess.run(
            ["git", "apply", str(patch)],
            cwd=base, check=True, timeout=20,
        )
    rewritten = path.read_text()
    assert len(rewritten) > len(original)
    begin = rewritten.index("void MapPages(Common::PageTable&")
    end = rewritten.index("template<typename F, typename G>", begin)
    mapping = rewritten[begin:end]
    assert mapping.count("EDEN_GUEST_MAP_NO_BACKING") == 1
    assert mapping.count("if (backing == nullptr)") == 1
    assert mapping.count("invalid.Store(false, Common::PageType::Unmapped") == 1
    assert mapping.index("if (backing == nullptr)") < mapping.index(
        "auto& entry = page_table.entries.GetUnchecked(base)")
    assert "IsDirectBackingAlias(base << YUZU_PAGEBITS, YUZU_PAGESIZE)" in mapping
    assert mapping.index("auto host_ptr = reinterpret_cast<u64>(backing)") < mapping.index(
        "IsDirectBackingAlias(base << YUZU_PAGEBITS, YUZU_PAGESIZE)")
    assert "if (IsDirectBackingAlias(vaddr, 1))" in rewritten
    assert "on_memory(offset, copy_amount, reinterpret_cast<u8*>(current_vaddr))" in rewritten
    assert "(addr + size - 1) >> YUZU_PAGEBITS" in rewritten
    assert "EDEN_GUEST_MAP_POINTER_ZERO" in rewritten
print("PASS exact pinned Eden src/core/memory.cpp git blob and 5 ordered production patch replays")
print("No PS5 native compilation, runtime driver, GPU frames or heap reclaim qualified")
