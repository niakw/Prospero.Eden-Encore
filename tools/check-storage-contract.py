#!/usr/bin/env python3
"""Compile and exercise Encore's exact storage-root selection contract."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source_text = (root / "headless/prosperoeden/eden_services.cpp").read_text()
start = source_text.index("bool EdenServices::set_files_folder(")
end = source_text.index("\nint EdenServices::filesystem_access()", start)
function = source_text[start:end]

harness = r'''
#include <cassert>
#include <filesystem>
#include <string>
#include <string_view>
#include <system_error>

namespace Eden {
static bool access = true;
static std::string saved;
bool FilesystemAccess() { return access; }
bool ValidAssetsDir(std::string_view path) {
    return !path.empty() && path != "/" && path.front() == '/' && path.back() != '/';
}
bool SaveAssetsDir(std::string_view directory) {
    saved = std::string(directory);
    return true;
}
void Report(const char*, const char*) {}
}

struct EdenServices {
    bool set_files_folder(const std::string& directory);
};

FUNCTION

int main(int argc, char** argv) {
    assert(argc == 2);
    namespace fs = std::filesystem;
    const fs::path base = argv[1];
    const fs::path root = base / "external";
    fs::create_directories(root);

    // Valid external root => exactly the standard schema is prepared and one root is saved.
    assert(EdenServices{}.set_files_folder(root.string()));
    for (const char* name : {"keys", "firmware", "roms", "updates", "mods",
                             "save-import", "save-export", "ryujinx"})
        assert(fs::is_directory(root / name));
    assert(Eden::saved == root.string());

    // Root symlink => reject.
    fs::remove_all(base / "link");
    std::error_code error;
    fs::create_directory_symlink(root, base / "link", error);
    if (!error)
        assert(!EdenServices{}.set_files_folder((base / "link").string()));

    // Standard child symlink => reject instead of following it.
    fs::remove_all(root / "roms");
    fs::create_directories(base / "outside");
    error.clear();
    fs::create_directory_symlink(base / "outside", root / "roms", error);
    if (!error)
        assert(!EdenServices{}.set_files_folder(root.string()));

    // No elevated filesystem access => external/internal root selection is unavailable.
    Eden::access = false;
    assert(!EdenServices{}.set_files_folder(root.string()));
}
'''.replace("FUNCTION", function)

with tempfile.TemporaryDirectory(prefix="eden-storage-contract-") as tmp:
    tmp = Path(tmp)
    source = tmp / "test.cpp"
    binary = tmp / "test"
    source.write_text(harness)
    subprocess.run(["clang++-18", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(tmp / "fs")], check=True)

print("Storage contract: fixed schema, symlink rejection and access gate PASS")
