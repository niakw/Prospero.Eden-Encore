#!/usr/bin/env python3
"""Exercise the exact writable-root proof used before Encore touches persistent storage."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = root / "headless/filesystem_probe.h"
source = r"""
#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>
#include "filesystem_probe.h"

int main(int argc, char** argv) {
    assert(argc == 2);
    namespace fs = std::filesystem;
    const fs::path base = argv[1];

    // Clean install: the root is created and the temporary proof file is removed.
    const fs::path clean = base / "clean";
    assert(Eden::ProbeWritableRoot(clean.string()));
    assert(fs::is_directory(clean));
    for (const auto& entry : fs::directory_iterator(clean))
        assert(entry.path().filename().string().find(".encore-access-probe-") != 0);

    // Existing real directory remains usable.
    assert(Eden::ProbeWritableRoot(clean.string()));

    // A regular file can never become a storage root.
    const fs::path file = base / "file";
    std::ofstream(file) << "x";
    assert(!Eden::ProbeWritableRoot(file.string()));

    // Never follow a symlink supplied as the root.
    const fs::path target = base / "target";
    fs::create_directories(target);
    const fs::path link = base / "link";
    std::error_code error;
    fs::create_directory_symlink(target, link, error);
    if (!error)
        assert(!Eden::ProbeWritableRoot(link.string()));
}
"""
with tempfile.TemporaryDirectory(prefix="encore-fs-probe-") as tmp:
    tmp = Path(tmp)
    cpp = tmp / "probe.cpp"
    exe = tmp / "probe"
    cpp.write_text(source)
    subprocess.run([
        "clang++-18", "-std=c++20", "-Wall", "-Wextra", "-Werror",
        "-I", str(root / "headless"), str(cpp), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe), str(tmp / "root")], check=True)

print("Filesystem root proof: create, write, cleanup and symlink rejection PASS")
