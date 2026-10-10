#!/usr/bin/env python3
"""Host ASan/UBSan+TSan regression for PS5 GPU process registry lifetime.

Models the intended locking, no-reuse and range checks. The pinned source
patch is validated separately; this is NOT a PS5 native driver execution.
"""
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = root / "tools/fixtures/gpu-asid-lifetime-host.cpp"
text = src.read_text(encoding="utf-8")
assert "std::shared_mutex guard" in text
assert "entries[id] = nullptr" in text
assert "entries.emplace_back(p)" in text
assert "assert(next != old)" in text
assert "kDeviceSize - address" in text
assert "process.reset()" in text
backport = (root / "headless/backports/eden-ps5-gpu-asid-lifetime-guard.patch").read_text()
retire = (root / "headless/backports/eden-ps5-gpu-asid-no-reuse.patch").read_text()
for token in ("process_registry_guard", "shared_lock", "unique_lock",
              "registered_processes[asid.id] == nullptr"):
    assert token in backport
for token in ("constexpr size_t max_ids", "registered_processes.emplace_back",
              "id_pool.push_front(asid.id);"):
    assert token in retire
assert "+    id_pool.push_front(asid.id);" not in retire
compiler = next((c for c in ("clang++-18", "clang++", "g++") if shutil.which(c)), None)
if not compiler:
    raise SystemExit("No C++20 compiler; refusing an unexecuted PASS")

with tempfile.TemporaryDirectory(prefix="eden-asid-lifetime-") as dirname:
    path = Path(dirname)
    executable = path / "asid-asan"
    flags = ["-std=c++20", "-O1", "-g", "-pthread", "-Wall", "-Wextra",
             "-Werror", "-fno-sanitize-recover=all"]
    subprocess.run([compiler, *flags, "-fsanitize=address,undefined",
                    str(src), "-o", str(executable)], check=True, timeout=90)
    subprocess.run([str(executable)], check=True, timeout=90)
    if platform.system() == "Linux" and platform.machine() in ("x86_64", "aarch64"):
        binary = path / "asid-tsan"
        subprocess.run([compiler, *flags, "-fsanitize=thread",
                        str(src), "-o", str(binary)], check=True, timeout=90)
        subprocess.run([str(binary)], check=True, timeout=180)
print("PASS host GPU ASID model; native interop/thread lifecycle remains unqualified")
