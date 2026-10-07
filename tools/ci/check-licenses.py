#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Release gate for legal notices, license bundle and project-authored launcher SFX."""
from pathlib import Path
import subprocess
import tempfile
import wave

root = Path(__file__).resolve().parents[2]
licenses = root / "LICENSES"
required_licenses = {
    "README.md", "ProsperoEden.txt", "Eden.txt", "FFmpeg.txt", "OpenSSL.txt",
    "zlib.txt", "LLVM.txt", "PS5-Vulkan-Mihawk.txt", "ps5-vulkan.txt",
    "PS5-Payload-SDK.txt", "Mihawk-PS5-PayloadSDK.txt",
    "PS5-Native-App-Boilerplate.txt", "ProsperoPuzzles.txt", "Nlib-API.txt",
    "HarfBuzz.txt", "stb.txt", "fmt.txt", "Boost.txt", "Xbyak.txt", "zstd.txt",
    "LZ4.txt", "Opus.txt", "SDL.txt", "simpleini.txt", "SPIRV-Headers.txt",
    "Vulkan-Headers.txt", "Vulkan-Utility-Libraries.txt",
    "VulkanMemoryAllocator.txt", "ENet.txt", "frozen.txt", "cpp-httplib.txt",
    "nlohmann-json.txt", "Montserrat-OFL-1.1.txt", "ZBIC-zstd-BSD.txt",
    "GPL-3.0-or-later.txt", "LGPL-2.1-or-later.txt", "Apache-2.0.txt",
}
required_licenses |= {
    f"Eden-{name}.txt" for name in (
        "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "BSL-1.0", "CC-BY-4.0",
        "CC-BY-SA-3.0", "CC0-1.0", "GPL-2.0-or-later", "GPL-3.0-or-later",
        "LGPL-3.0-or-later", "LLVM-exception", "MIT", "MPL-2.0", "Unlicense",
        "WTFPL", "Zlib",
    )
}
required_licenses |= {
    "Dynarmic.txt", "Sirit.txt", "PS5-OpenGL.txt",
    "Mesa-license.rst", "Mesa-Apache-2.0.txt", "Mesa-BSL-1.0.txt",
    "Mesa-GPL-1.0-or-later.txt", "Mesa-GPL-2.0-only.txt", "Mesa-MIT.txt",
    "Mesa-SGI-B-2.0.txt", "Mesa-Linux-Syscall-Note.txt",
}
missing = sorted(required_licenses - {p.name for p in licenses.iterdir() if p.is_file()})
assert not missing, f"missing bundled license texts: {missing}"
assert all((licenses / name).stat().st_size > 250 for name in required_licenses)

notices = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
readme = (root / "README.md").read_text(encoding="utf-8")
for marker in (
    "Encore selects the BSD-style terms",
    "does **not** represent Nlib-served media as",
    "Copyright licensing and trademark rights are separate",
    "generated deterministically by `tools/launcher/generate-sfx.py`",
):
    assert marker in notices, marker
for marker in ("unofficial community fork", "Nlib is queried at runtime", "without warranty"):
    assert marker in readme, marker
# The current tree must not contain a literal reference to the removed audio service.
needle = ("eleven" + "labs").encode("ascii")
for raw in subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0"):
    if not raw:
        continue
    path = root / raw.decode("utf-8")
    if path.is_file():
        assert needle not in path.read_bytes().lower(), f"removed audio-service reference remains: {path}"

packager = (root / "tools/package-headless-native.sh").read_text(encoding="utf-8")
staged_check = (root / "tools/ci/check-staged-app.py").read_text(encoding="utf-8")
dist = (root / "tools/ci/make-dist.py").read_text(encoding="utf-8")
assert 'cp "$root/LICENSE" "$root/THIRD_PARTY_NOTICES.md" "$app/legal/"' in packager
assert 'cp -a "$root/LICENSES" "$app/legal/LICENSES"' in packager
assert 'legal/THIRD_PARTY_NOTICES.md' in staged_check
assert "'LICENSES/' + p.name" in dist

sound_dir = root / "headless/prosperoeden/ui/sounds"
expected_sounds = {
    "back_01.wav", "error_01.wav", "focus_01.wav", "focus_02.wav", "launch_01.wav",
    "modal_close_01.wav", "modal_open_01.wav", "notify_01.wav", "open_01.wav", "page_01.wav",
    "resume_01.wav", "saved_01.wav", "select_01.wav", "slider_01.wav", "slider_02.wav",
    "slider_03.wav", "toggle_01.wav", "toggle_02.wav", "toggle_03.wav", "welcome_01.wav",
}
assert {p.name for p in sound_dir.glob("*.wav")} == expected_sounds
for path in sound_dir.glob("*.wav"):
    with wave.open(str(path), "rb") as stream:
        assert stream.getframerate() == 48_000 and stream.getsampwidth() == 2
        assert stream.getnchannels() in (1, 2) and stream.getnframes() > 1000

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    subprocess.run(["python3", str(root / "tools/launcher/generate-sfx.py"), str(tmp)],
                   check=True, stdout=subprocess.DEVNULL)
    for name in expected_sounds:
        assert (tmp / name).read_bytes() == (sound_dir / name).read_bytes(), f"stale SFX: {name}"

print(f"Legal/license/SFX release gate PASS ({len(required_licenses)} license files, {len(expected_sounds)} authored sounds)")
