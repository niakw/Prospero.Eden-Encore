#!/usr/bin/env python3
"""Replay all PS5 GPU translation patches on exact pinned Eden source.

Reads only two public pinned files and verifies their Git blob hashes before
replaying 16 production ordered patches with git apply. Host only: no PS5 SDK,
no user machine files, no GPU runtime and no source modifications outside the
ephemeral CI worker.
"""
import hashlib
import re
import sys
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

root = Path(__file__).resolve().parents[1]
pin = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
manifest = {
    "src/core/device_memory_manager.inc": "97c2706abbecf1e7d59f32ab9b31ba3d2c372c2c",
    "src/core/device_memory_manager.h": "b4b3b46088e5d9165f7df99372137237c00ac303",
}
patch_names = (
    "eden-ps5-gpu-memory-mapping.patch",
    "eden-ps5-gpu-remap-reverse.patch",
    "eden-ps5-gpu-unmap-reverse-guard.patch",
    "eden-ps5-gpu-multi-missing-guard.patch",
    "eden-ps5-gpu-map-bounds.patch",
    "eden-ps5-gpu-physical-capacity.patch",
    "eden-ps5-gpu-remap-cache-invalidate.patch",
    "eden-ps5-gpu-empty-multi-head.patch",
    "eden-ps5-gpu-physical-read-bounds.patch",
    "eden-ps5-gpu-block-flush-bounds.patch",
    "eden-ps5-gpu-span-physical-bounds.patch",
    "eden-ps5-gpu-reverse-inline-bounds.patch",
    "eden-ps5-gpu-atomic-forward-table.patch",
    "eden-ps5-gpu-atomic-reverse-table.patch",
    "eden-ps5-gpu-asid-lifetime-guard.patch",
    "eden-ps5-gpu-asid-no-reuse.patch",
)
apply_source = (root / "tools/apply-eden-backports.sh").read_text()
assert f"expected={pin}" in apply_source
positions = [apply_source.index(f'apply_one "$root/headless/backports/{name}"')
             for name in patch_names]
assert positions == sorted(positions), "Actual backport order differs"

with tempfile.TemporaryDirectory(prefix="eden-pinned-gpu-replay-") as tmp:
    checkout = Path(tmp)
    for rel, known_blob in manifest.items():
        url = f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}"
        last_error = None
        for attempt in range(3):
            try:
                request = Request(url, headers={"User-Agent": "Encore-pinned-GPU-replay"})
                with urlopen(request, timeout=20) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Unexpected upstream HTTP {response.status}")
                    data = response.read(1024 * 1024 + 1)
                    if len(data) > 1024 * 1024:
                        raise RuntimeError("Too much data in pinned GPU source")
                break
            except (TimeoutError, OSError, HTTPError, URLError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(1)
        else:
            raise SystemExit(f"Pinned GPU source cannot be verified: {rel}: {last_error}")
        actual = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if actual != known_blob:
            raise SystemExit(f"PIN SHA DRIFT {rel}: {actual} != {known_blob}")
        dest = checkout / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    for name in patch_names:
        patch = root / "headless/backports" / name
        if not patch.is_file():
            raise SystemExit(f"Missing production GPU patch: {name}")
        print("VERIFY_GUEST_GPU_PATCH", name, flush=True)
        subprocess.run(["git", "apply", "--check", str(patch)],
                       cwd=checkout, check=True, timeout=20)
        subprocess.run(["git", "apply", str(patch)],
                       cwd=checkout, check=True, timeout=20)
    merged_inc = (checkout / "src/core/device_memory_manager.inc").read_text()
    merged_h = (checkout / "src/core/device_memory_manager.h").read_text()
    for needle in (
        "EDEN_GPU_REMAP_REVERSE_MISMATCH",
        "EDEN_GPU_REMAP_MULTI_MISSING",
        "EDEN_GPU_MAP_BAD_RANGE",
        "EDEN_GPU_MAP_OUTSIDE_DRAM",
        "EDEN_GPU_READ_WRITE_PHYS_OOB",
        "EDEN_GPU_UNMAP_REVERSE_MISMATCH",
        "EDEN_GPU_REMAP_MULTI_MISSING",
        "__atomic_load_n(",
        "__atomic_store_n(",
    ):
        assert needle in merged_inc or needle in merged_h, needle
    assert "registered_processes.emplace_back(memory_device_inter)" in merged_inc
    assert "std::shared_lock registry_lk(process_registry_guard)" in merged_inc
    assert "std::atomic_ref" not in merged_h
    assert merged_h.count("__atomic_load_n(") == 4
    assert merged_h.count("__atomic_store_n(") == 4
    # Native C++17 SDK cannot instantiate C++20 std::atomic_ref.
    assert "__ATOMIC_ACQUIRE" in merged_h and "__ATOMIC_RELEASE" in merged_h
    assert "device_inter->InvalidateRegion(address, size);" in merged_inc
    # Protect both GetSpan overloads independently, never count their tokens
    # across the entire source: WalkBlock legitimately uses the same guard.
    span_need = ("first_phys >= compressed_device_addr.size()",
                 "page_count > compressed_device_addr.size() - first_phys")
    for signature in ("u8* DeviceMemoryManager<Traits>::GetSpan(",
                      "const u8* DeviceMemoryManager<Traits>::GetSpan("):
        start = merged_inc.index(signature)
        end = merged_inc.index("template <typename Traits>", start)
        block = merged_inc[start:end]
        for token in span_need:
            assert block.count(token) == 1, (signature, token)
        assert (block.index("if (backing == 0) return nullptr;") <
                block.index(span_need[0]) < block.index(span_need[1]) <
                block.index("for (size_t i = 1; i < page_count; ++i)"))
    # Non-GetSpan guard is required too; global two-hit counts are unsafe.
    walk = merged_inc[merged_inc.index("void DeviceMemoryManager<Traits>::WalkBlock("):
                      merged_inc.index("void DeviceMemoryManager<Traits>::ReadBlock(")]
    assert span_need[0] in walk
    apply_source_guard = ("if s.count(token) != 2:")
    assert apply_source_guard not in apply_source
    assert "tracked_entries[first_page + i].compressed_physical_ptr != backing + i" not in merged_inc, (
        "A pinned physical-page patch must update raw table access to atomic helpers")
    # Prove production cache-resume behavior, not merely the 16 git apply hunks:
    # apply_one() reruns each early-stage validator against a FULLY patched
    # cached Eden tree, which must accept later security-hardening edits.
    replay_count = 0
    failed_validators = []
    for name in patch_names:
        binding = re.search(
            r'(?m)^apply_one "\$root/headless/backports/' + re.escape(name) +
            r'" "[^"]+" (validate_ps5_gpu_\w+)$', apply_source)
        assert binding, "Missing production GPU validator binding: " + name
        validator_name = binding.group(1)
        script = re.search(
            r"(?ms)^" + re.escape(validator_name) +
            r"\(\) \{\npython3 - \"\$eden\" <<'(\w+)'\n(.*?)\n\1\n\}",
            apply_source)
        assert script, "Cannot extract production validator: " + validator_name
        result = subprocess.run([sys.executable, "-c", script.group(2), str(checkout)],
                                cwd=checkout, capture_output=True, text=True,
                                timeout=20)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            failed_validators.append((validator_name, detail))
            print("GPU_CACHE_VALIDATOR_FAIL", validator_name, detail, flush=True)
        else:
            print("GPU_CACHE_VALIDATOR_PASS", validator_name, flush=True)
        replay_count += 1
    assert replay_count == len(patch_names)
    if failed_validators:
        raise SystemExit("Cached GPU source revalidation failed in " +
                         str(len(failed_validators)) + " of " + str(replay_count) +
                         " stages: " + repr(failed_validators))
    print(f"PASS cached fully-patched Eden GPU: {replay_count} actual stage validators", flush=True)

print("PASS two exact pinned GPU sources, all 16 production-ordered git apply patches")
print("No PS5 native compilation, shader/framebuffer output or runtime performance proof")
