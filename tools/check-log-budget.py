#!/usr/bin/env python3
from pathlib import Path
root = Path(__file__).resolve().parents[1]
pipe = (root / "headless/log_pipe.h").read_text()
main = (root / "headless/main.cpp").read_text()
patch = (root / "headless/backports/eden-ps5-bounded-logging.patch").read_text()
apply = (root / "tools/apply-eden-backports.sh").read_text()

assert "segment_limit = 8u * 1024u * 1024u" in pipe
for name in ('previous = Eden::LogFile', 'previous_first = Eden::LogFile',
             'std::remove(previous.c_str())', 'std::remove(previous_first.c_str())'):
    assert name in main, name
for needle in ('constexpr auto write_limit = 8_MiB;', 'void RotatePs5() noexcept',
               'log tail rotated; storage remains bounded', 'file->SetSize(0)'):
    assert needle in patch, needle
assert 'eden-ps5-bounded-logging.patch' in apply
assert 'filter.ParseFilterString("*:Debug")' not in main
print("Bounded PS5 logs + one-session cleanup: PASS")
