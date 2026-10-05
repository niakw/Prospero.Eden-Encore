#!/usr/bin/env python3
"""Compile and exercise Encore's exact legacy ProsperoEden game-files migration."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = (root / "headless/main.cpp").read_text()
start = main.index("static bool LegacyGameFilesRemain(")
end = main.index("static void MigrateSandboxData()", start)
migration = main[start:end]

harness = r'''
#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>
#include <vector>

namespace Eden {
const char* kLegacyInstallAssetsDir = nullptr;
const char* kDefaultAssetsDir = nullptr;
static std::string saved;
static std::vector<std::string> reports;

bool LegacyAppAssetsPath(std::string_view path) {
    return path == kLegacyInstallAssetsDir || path == "/app0/assets" ||
           path == "/system_ex/app/PPSA99008/assets" ||
           path == "/mnt/sandbox/PPSA99008_000/app0/assets";
}
bool DirectoryExists(const std::string& path) {
    std::error_code error;
    return std::filesystem::is_directory(path, error) && !error;
}
std::string LoadSavedAssetsDir() { return saved; }
bool SaveAssetsDir(std::string_view directory) {
    saved = std::string(directory);
    return true;
}
void Report(const char*, const char* detail) { reports.emplace_back(detail ? detail : ""); }
}

MIGRATION

static void file(const std::filesystem::path& p) {
    std::filesystem::create_directories(p.parent_path());
    std::ofstream(p) << "x";
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::filesystem::path base = argv[1];
    const auto legacy = base / "app/assets";
    const auto target = base / "data";
    const auto custom = base / "custom";
    std::string legacy_s = legacy.string(), target_s = target.string();
    Eden::kLegacyInstallAssetsDir = legacy_s.c_str();
    Eden::kDefaultAssetsDir = target_s.c_str();

    // 1. Active legacy folder: move its known game-data directories, preserve bytes, update setting.
    std::filesystem::remove_all(base);
    file(legacy / "keys/prod.keys");
    file(legacy / "roms/game.nsp");
    Eden::saved = legacy_s;
    MigrateLegacyInstallAssets();
    assert(!std::filesystem::exists(legacy / "keys"));
    assert(!std::filesystem::exists(legacy / "roms"));
    assert(std::filesystem::exists(target / "keys/prod.keys"));
    assert(std::filesystem::exists(target / "roms/game.nsp"));
    assert(Eden::saved == target_s);

    // 2. Explicit custom folder: old historical app assets must not be moved.
    std::filesystem::remove_all(base);
    file(legacy / "roms/old.nsp");
    file(custom / "roms/current.nsp");
    Eden::saved = custom.string();
    MigrateLegacyInstallAssets();
    assert(std::filesystem::exists(legacy / "roms/old.nsp"));
    assert(std::filesystem::exists(custom / "roms/current.nsp"));
    assert(Eden::saved == custom.string());

    // 3. Destination conflict: never overwrite/merge silently; preserve the legacy selection.
    std::filesystem::remove_all(base);
    file(legacy / "roms/legacy.nsp");
    file(target / "roms/new.nsp");
    Eden::saved = legacy_s;
    MigrateLegacyInstallAssets();
    assert(std::filesystem::exists(legacy / "roms/legacy.nsp"));
    assert(std::filesystem::exists(target / "roms/new.nsp"));
    assert(Eden::saved == legacy_s);

    // 4. App removed first: repair the now-dead legacy selection to the persistent data root.
    std::filesystem::remove_all(base);
    std::filesystem::create_directories(target);
    Eden::saved = legacy_s;
    MigrateLegacyInstallAssets();
    assert(Eden::saved == target_s);
}
'''.replace("MIGRATION", migration)

with tempfile.TemporaryDirectory(prefix="eden-legacy-migration-") as tmp:
    tmp = Path(tmp)
    source = tmp / "test.cpp"
    binary = tmp / "test"
    source.write_text(harness)
    subprocess.run(["clang++-18", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(tmp / "fs")], check=True)

print("Legacy ProsperoEden migration: move, custom-folder preservation, conflict safety and stale-path repair PASS")
