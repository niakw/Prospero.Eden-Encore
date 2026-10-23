#!/usr/bin/env python3
"""Host-proof the selected ExeFS game folder and saved ROM path contract.

Compile the *real* game_files.h and actual ValidRomFilename function in a
standalone host fixture, with and without optimisation and under UBSan.
This is not PS5 load/runtime qualification.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "headless/game_files.h").read_text()
settings = (root / "headless/settings_store.h").read_text()
library = (root / "headless/prosperoeden/eden_services.cpp").read_text()
main = (root / "headless/main.cpp").read_text()
start_key = "inline bool ValidRomFilename(std::string_view name) {"
assert settings.count(start_key) == 1
start = settings.index(start_key)
end = settings.index("\n}\n", start) + 2
actual_validator = settings[start:end]
assert "IsDeconstructedGameSelection(name)" in actual_validator
assert "c == '/' && !exefs" in actual_validator
assert 'IsDeconstructedGameDirectory(entry.path())' in library
assert 'if (!Eden::ValidRomFilename(file)) continue;' in library
assert 'game.name = CleanTitle(entry_name);' in library
assert 'game.format = format;' in library
assert 'CountExeFsFolders(roms_path)' in library
assert 'IsDeconstructedGameDirectory(selected_path.parent_path())' in main
assert 'Eden::IsDeconstructedGameDirectory(entry.path())' in main
assert 'selected_path.filename() == "main"' in main
assert "symlink_status(folder / name, error)" in header

source = r"""
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <string_view>
#include <unistd.h>
#include "game_files.h"
namespace Eden {
VALIDATOR
}
int main() {
    namespace fs = std::filesystem;
    char format[] = "/tmp/eden-exefs-XXXXXX";
    char* tmp = ::mkdtemp(format);
    assert(tmp != nullptr);
    fs::path root{tmp};
    const fs::path rom = root / "My Game";
    fs::create_directories(rom);
    std::ofstream(rom / "main") << "code";
    std::ofstream(rom / "main.npdm") << "metadata";
    assert(Eden::IsDeconstructedGameDirectory(rom));
    assert(Eden::IsDeconstructedGameSelection("My Game/main"));
    assert(Eden::ValidRomFilename("My Game/main"));
    assert(Eden::ValidRomFilename("game.NSZ"));
    assert(Eden::ValidRomFilename("game.NAX"));
    assert(!Eden::ValidRomFilename("../main"));
    assert(!Eden::ValidRomFilename("My Game/../main"));
    assert(!Eden::ValidRomFilename("My Game/sub/main"));
    assert(!Eden::ValidRomFilename("/main"));
    assert(!Eden::ValidRomFilename("main"));
    assert(!Eden::ValidRomFilename("My Game\\main"));
    assert(!Eden::ValidRomFilename("game.zst"));
    assert(!Eden::ValidRomFilename("folder/main/extra"));
    fs::remove(rom / "main.npdm");
    assert(!Eden::IsDeconstructedGameDirectory(rom));
    fs::create_symlink(rom / "main", rom / "main.npdm");
    assert(!Eden::IsDeconstructedGameDirectory(rom));
    fs::remove(rom / "main.npdm");
    std::ofstream(rom / "main.npdm") << "metadata";
    fs::rename(rom / "main", rom / "real_main");
    fs::create_symlink(rom / "real_main", rom / "main");
    assert(!Eden::IsDeconstructedGameDirectory(rom));
    fs::remove(rom / "main");
    fs::rename(rom / "real_main", rom / "main");
    assert(Eden::IsDeconstructedGameDirectory(rom));
    const fs::path linked = root / "symlinked-game";
    fs::create_directory_symlink(rom, linked);
    assert(!Eden::IsDeconstructedGameDirectory(linked));
    fs::remove_all(root);
    std::puts("EXEFS_DIRECTORY_AND_SELECTION_PASS");
}
""".replace("VALIDATOR", actual_validator)

compilers = [exe for exe in (shutil.which("clang++"), shutil.which("g++"))
             if exe]
assert compilers, "C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-exefs-host-") as temp:
    cpp = Path(temp) / "test.cpp"
    cpp.write_text(source)
    for compiler in dict.fromkeys(compilers):
        for opt in ("-O0", "-O2"):
            exe = Path(temp) / (Path(compiler).name + opt)
            built = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(root / "headless"), str(cpp), "-o", str(exe)],
                capture_output=True, text=True, timeout=60
            )
            assert built.returncode == 0, (compiler, opt, built.stderr[-4000:])
            check = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
            assert check.returncode == 0 and "EXEFS_DIRECTORY_AND_SELECTION_PASS" in check.stdout, (
                compiler, opt, check.stdout, check.stderr[-4000:]
            )
            print("EXEFS_REAL_SOURCE_HOST_PASS", Path(compiler).name, opt)
