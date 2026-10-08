#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=(root/'headless/main.cpp').read_text()
patch=(root/'headless/backports/eden-ps5-bounded-logging.patch').read_text()
apply=(root/'tools/apply-eden-backports.sh').read_text()
assert 'kReleaseLogSegmentBytes = 8u * 1024u * 1024u' in main
assert main.count('kReleaseLogSegmentBytes') == 3
for needle in (
    'constexpr auto write_limit = 8_MiB;',
    'void RotatePs5() noexcept',
    'first_filename += ".first.txt"',
    'file->SetSize(0)',
    'log tail rotated; storage remains bounded',
):
    assert needle in patch, needle
assert 'validate_ps5_bounded_logging' in apply
assert 'eden-ps5-bounded-logging.patch' in apply
# FS::IOFile logs its own errors; it must not recurse into this file backend
# if a disk-full / refused-truncate error occurs mid-rotation.
rotation = patch.split('+    void RotatePs5() noexcept {', 1)[1].split('+    std::filesystem::path filename;', 1)[0]
assert '+        enabled = false;' in rotation
assert '+        enabled = file->IsOpen();' in rotation
assert 'Re-entrant' in rotation
# The PS5 branch rotates; only the non-PS5 fallback is allowed to disable on cap.
ps5=patch[patch.index('+#ifdef PS5_NATIVE', patch.index('using namespace Common::Literals;')):
          patch.index('+#else', patch.index('+#ifdef PS5_NATIVE', patch.index('using namespace Common::Literals;')))]
assert 'enabled = false' not in ps5
print('Bounded circular release log policy PASS')
