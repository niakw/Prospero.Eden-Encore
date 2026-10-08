#!/usr/bin/env python3
"""Host-only bounded log-pipe regression, including a refused ftruncate.

Compiles a tiny temporary C++ harness, NOT the PS5 application. The stub forces
the O_TRUNC recovery path used when a native filesystem rejects ftruncate().
"""
from pathlib import Path
import os
import shutil
import sys
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = r"""
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>
#include <sys/types.h>
#include <unistd.h>

extern "C" int reject_truncate(int, off_t);
#define ftruncate reject_truncate
#include "log_pipe.h"
#undef ftruncate
extern "C" int reject_truncate(int, off_t) { errno = EINVAL; return -1; }

int main(int argc, char **argv) {
    assert(argc == 3);
    std::FILE *out = std::fopen(argv[1], "w");
    assert(out);
    {
        Eden::LogPipe pipe;
        assert(pipe.Attach(out, argv[1], argv[2], 64u * 1024u));
        for (int i = 0; i < 11000; ++i) {
            std::fprintf(out, "log-entry-%05d-abcdefghijklmnopqrstuvwxyz0123456789\n", i);
        }
        std::fflush(out);
        pipe.Detach();
    }
    assert(std::fclose(out) == 0);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="encore-log-pipe-unit-") as tmp:
    path = Path(tmp)
    src = path / "log_unit.cpp"
    binary = path / "log_unit"
    recent = path / "stderr.log"
    first = path / "stderr.first.log"
    src.write_text(source)
    env = dict(os.environ)
    env.setdefault("SDKROOT", "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk")
    cxx = shutil.which("clang++") if sys.platform == "darwin" else (shutil.which("clang++-18") or shutil.which("clang++"))
    assert cxx is not None, "Clang++ is required for host log-pipe micro-test"
    subprocess.run(
        [cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror",
         "-pthread", "-I", str(root / "headless"), str(src), "-o", str(binary)],
        check=True, env=env, capture_output=True, text=True,
    )
    subprocess.run([str(binary), str(recent), str(first)], check=True, env=env, timeout=12)
    assert recent.is_file() and first.is_file()
    assert 0 < recent.stat().st_size <= 82 * 1024, recent.stat().st_size
    assert 0 < first.stat().st_size <= 82 * 1024, first.stat().st_size
    assert "log-entry-10999" in recent.read_text()
    assert "log-entry-00000" in first.read_text()
    print("LogPipe bounded rotation + refused ftruncate recovery: host unit PASS")
