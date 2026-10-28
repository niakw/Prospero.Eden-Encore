#!/usr/bin/env python3
"""Exercise reproducibility diagnostics with equal, changed and short images."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
script = root / "tools/ci/diagnose-image-repro.py"
make_dist = (root / "tools/ci/make-dist.py").read_text()
assert "tools/ci/diagnose-image-repro.py" in make_dist
assert "if repro_digest != image_digest:" in make_dist
assert "raise SystemExit(f'FFPFSC reproducibility check failed:" in make_dist
assert "image.replace(repro)" in make_dist
assert "str(app), str(image)], check=True)" in make_dist
assert "image.unlink(missing_ok=True)" in make_dist
assert "repro.replace(image)" in make_dist
assert make_dist.index("image.replace(repro)") < make_dist.index(
    "repro_digest = hashlib.sha256(image.read_bytes()).hexdigest()") < make_dist.index(
    "repro.replace(image)")

with tempfile.TemporaryDirectory(prefix="encore-pfs-diff-") as tmp:
    left = Path(tmp) / "a.ffpfsc"
    right = Path(tmp) / "b.ffpfsc"
    payload = bytearray(b"A" * (1024 * 1024 + 12))
    left.write_bytes(payload)
    right.write_bytes(payload)
    same = subprocess.run([sys.executable, str(script), str(left), str(right)],
                          capture_output=True, text=True, check=True)
    assert "first_different_offset=None" in same.stdout
    payload[1024 * 1024 + 5] = ord("B")
    right.write_bytes(payload)
    diff = subprocess.run([sys.executable, str(script), str(left), str(right)],
                          capture_output=True, text=True)
    assert diff.returncode == 1
    assert "first_different_offset=1048581" in diff.stdout
    assert "offset=0x100005" in diff.stdout
    right.write_bytes(bytes(payload[:100]))
    short = subprocess.run([sys.executable, str(script), str(left), str(right)],
                           capture_output=True, text=True)
    assert short.returncode == 1
    assert "first_different_offset=100" in short.stdout
    assert "a=41 b=EOF" in short.stdout
print("FFPFSC_REPRO_DIAGNOSTIC_PASS")
