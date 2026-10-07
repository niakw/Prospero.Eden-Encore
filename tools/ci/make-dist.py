#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Release files from a built PPSA99008 folder (make release, make image).

  tools/ci/make-dist.py [--image-only] APP_DIR

dist/Prospero.Eden-Encore-RN.zip (the folder plus README, INSTALL, SECURITY, LICENSE,
THIRD_PARTY_NOTICES and LICENSES/; fixed timestamps, so equal inputs give equal bytes),
dist/Prospero.Eden-Encore-RN-FTP.zip (minimal PPSA99008 folder for manual FTP installs:
runtime files only, without installed legal texts or ShadowMount-only .txt language companions),
dist/Prospero.Eden-Encore-RN.ffpfsc
(the same title as a package image, tools/ci/package-image.sh), SHA256SUMS and release-notes.md.
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parents[2]
args = sys.argv[1:]
image_only = args[:1] == ['--image-only']
if image_only:
    args = args[1:]
if len(args) != 1:
    sys.exit(__doc__.strip())
app = pathlib.Path(args[0]).resolve()
version_h = (root / 'headless/prosperoeden/version.h').read_text()
match = re.search(r'kAppVersion\s*=\s*"([^"]+)"', version_h)
if not match:
    sys.exit('Cannot read Encore release name from version.h')
release = match.group(1)
dist = root / 'dist'
image = dist / f'Prospero.Eden-Encore-{release}.ffpfsc'
if image_only:
    dist.mkdir(exist_ok=True)
    subprocess.run(['bash', str(root / 'tools/ci/package-image.sh'), str(app), str(image)], check=True)
    print(f'{image} {hashlib.sha256(image.read_bytes()).hexdigest()}')
    sys.exit(0)
shutil.rmtree(dist, ignore_errors=True)
dist.mkdir()
archive = dist / f'Prospero.Eden-Encore-{release}.zip'
files = [(p, 'PPSA99008/' + p.relative_to(app).as_posix()) for p in sorted(app.rglob('*')) if p.is_file()]
files += [(root / name, name) for name in
          ('README.md', 'INSTALL.md', 'SECURITY.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')
          if (root / name).exists()]
files += [(p, 'LICENSES/' + p.name) for p in sorted((root / 'LICENSES').iterdir()) if p.is_file()]
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
    for path, name in files:
        info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zip_file.writestr(info, path.read_bytes())
digest = hashlib.sha256(archive.read_bytes()).hexdigest()

# Manual PS5 FTP servers commonly support binary STOR only. FileZilla may switch .txt files to
# ASCII automatically, so publish a separate runtime-only folder archive for manual FTP installs.
# The full ZIP and FFPFSC above remain the canonical distribution artifacts and keep every legal
# notice plus the ShadowMount .txt catalog companions.
ftp_archive = dist / f'Prospero.Eden-Encore-{release}-FTP.zip'
ftp_files = []
for path in sorted(app.rglob('*')):
    if not path.is_file():
        continue
    relative = path.relative_to(app)
    posix = relative.as_posix()
    if posix == 'legal' or posix.startswith('legal/'):
        continue
    if relative.parent.as_posix() == 'ui/lang' and relative.suffix == '.txt':
        continue
    ftp_files.append((path, 'PPSA99008/' + posix))
with zipfile.ZipFile(ftp_archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
    for path, name in ftp_files:
        info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zip_file.writestr(info, path.read_bytes())
ftp_digest = hashlib.sha256(ftp_archive.read_bytes()).hexdigest()

subprocess.run(['bash', str(root / 'tools/ci/package-image.sh'), str(app), str(image)], check=True)
image_digest = hashlib.sha256(image.read_bytes()).hexdigest()
# Prove the package-image path is deterministic before publishing its checksum. This catches a
# third-party timestamp/randomness regression instead of silently changing release bytes.
repro = dist / f'.{image.name}.repro'
try:
    subprocess.run(['bash', str(root / 'tools/ci/package-image.sh'), str(app), str(repro)], check=True)
    repro_digest = hashlib.sha256(repro.read_bytes()).hexdigest()
    if repro_digest != image_digest:
        raise SystemExit(f'FFPFSC reproducibility check failed: {image_digest} != {repro_digest}')
finally:
    repro.unlink(missing_ok=True)
(dist / 'SHA256SUMS').write_text(
    f'{digest}  {archive.name}\n'
    f'{ftp_digest}  {ftp_archive.name}\n'
    f'{image_digest}  {image.name}\n'
)
# The unstripped executable of this release, to name the functions in a crash report later
# (tools/symbolize-crash.py). Kept out of dist/: it is not a release file.
unstripped = root / 'build/headless-native/llvm-pie.elf'
if unstripped.exists():
    symbols = root / 'build/symbols' / f'Prospero.Eden-Encore-{release}.elf'
    symbols.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(unstripped, symbols)
    print(f'{symbols} (keep it with the release: crash reports are read with it)')
readme = (root / 'README.md').read_text()
heading = f'Encore {release}'
match = re.search(rf'^## Changes in {re.escape(heading)}\n(.*?)(?=^## )', readme, re.M | re.S)
if match:
    (dist / 'release-notes.md').write_text(match.group(1).strip() + '\n')
else:
    sys.exit(f'README.md has no "## Changes in {heading}" section; release notes are required')
print(f'{archive} {digest}')
print(f'{ftp_archive} {ftp_digest}')
print(f'{image} {image_digest}')
