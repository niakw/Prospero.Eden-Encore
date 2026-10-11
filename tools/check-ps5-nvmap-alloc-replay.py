#!/usr/bin/env python3
"""R311: replay PS5 nvmap invalid-device-lock fix against immutable Eden input."""
from pathlib import Path
import hashlib
import subprocess
import tempfile
from urllib.request import urlopen, Request

root = Path(__file__).resolve().parents[1]
patch_path = root / "headless/backports/eden-ps5-nvmap-alloc-rollback.patch"
source_path = "src/core/hle/service/nvdrv/devices/nvmap.cpp"
pinned = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
blob_sha = "a42b5682aa4de70683fb5fc579de3b816cabf622"
url = f"https://raw.githubusercontent.com/eden-emulator/mirror/{pinned}/{source_path}"
script = (root / "tools/apply-eden-backports.sh").read_text()
assert "expected=" + pinned in script
assert script.count('apply_one "$root/headless/backports/' + patch_path.name + '"') == 1
assert "validate_ps5_nvmap_alloc_rollback" in script

if not patch_path.is_file():
    raise SystemExit("Missing production nvmap patch")
with urlopen(Request(url, headers={"User-Agent": "Encore-R311-pinned-source-replay"}),
             timeout=25) as response:
    payload = response.read(200_000)
actual = hashlib.sha1(
    b"blob " + str(len(payload)).encode() + b"\\0" + payload).hexdigest()
assert actual == blob_sha, (actual, blob_sha)
original = payload.decode("utf-8")
with tempfile.TemporaryDirectory(prefix="eden-r311-nvmap-") as directory:
    root_tmp = Path(directory)
    target = root_tmp / source_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    subprocess.run(["git", "apply", "--check", str(patch_path)],
                   cwd=directory, check=True, timeout=10)
    subprocess.run(["git", "apply", str(patch_path)],
                   cwd=directory, check=True, timeout=10)
    rewritten = target.read_text()
    start = rewritten.index("NvResult nvmap::IocAlloc(")
    end = rewritten.index("NvResult nvmap::IocGetId(", start)
    fn = rewritten[start:end]
    before = original[original.index("NvResult nvmap::IocAlloc("):
                      original.index("NvResult nvmap::IocGetId(")]
    assert before.count("ASSERT(process->GetPageTable()") == 1
    assert fn.count("ASSERT(process->GetPageTable()") == 1
    assert fn.count("handle_description->Alloc(") == 1
    assert fn.count("LockForMapDeviceAddressSpace(") == 2
    assert fn.index("if (!params.address)") < fn.index("handle_description->Alloc(")
    failure = fn[fn.index("if (!map_result.IsSuccess())"):
                 fn.index("#else", fn.index("if (!map_result.IsSuccess())"))]
    assert failure.index("handle_description->allocated = false;") < failure.index(
        "return NvResult::BadValue;")
    assert "handle_description->address = 0;" in failure
    assert "std::scoped_lock lock(handle_description->mutex);" in failure
    assert "UnlockForDeviceAddressSpace" not in failure
    assert "EDEN_NVMAP_REJECT_ZERO_ADDRESS" in fn
    assert "EDEN_NVMAP_MAP_FAILED" in fn
    assert "#else\n    ASSERT(process->GetPageTable()" in fn
    assert "return result;" == fn.strip().splitlines()[-2].strip()
print("R311 PASS: pinned Eden nvmap git-blob exact replay, fail-closed lock, rollback, original non-PS5 path")
