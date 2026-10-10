#!/usr/bin/env python3
"""Execute a PS5 GPU physical-read and GetSpan boundary model with C++ sanitizers.

This is NOT the actual Eden DeviceMemoryManager unit or a native PS5 build.
The source-bound patch invariants are checked separately by
tools/check-gpu-memory-mapping-source.py.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / "tools/fixtures/gpu-physical-bounds-host.cpp"
text = source.read_text(encoding="utf-8")
assert "GetSpanModel" in text and "ReadBlockModel" in text
assert "ReferenceRead" in text and "ReferenceSpan" in text
assert "tests == 24500" in text
compiler = next((name for name in ("clang++-18", "clang++", "c++")
                 if shutil.which(name)), None)
if compiler is None:
    raise SystemExit("C++20 compiler missing; no source-only false PASS")

with tempfile.TemporaryDirectory(prefix="eden-gpu-phys-cpp-") as folder:
    binary = Path(folder) / "gpu-physical-bounds"
    subprocess.run([compiler, "-std=c++20", "-O1", "-g",
                    "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all",
                    str(source), "-o", str(binary)], check=True, timeout=120)
    subprocess.run([str(binary)], check=True, timeout=120)
print("Only the host C++ model was executed; PS5 GPU runtime remains unqualified")
