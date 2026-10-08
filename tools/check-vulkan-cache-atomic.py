#!/usr/bin/env python3
"""Compile the EXACT PS5 Vulkan driver-cache serializer injected by the port.

Mocks only the vk::PipelineCache driver blob and logging. Tests replacement
of an existing cache, a failed staging write, and concurrent serializers.
This is NOT PS5 firmware/driver qualification.
"""
from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CXX = next((c for c in ("clang++-18", "clang++", "g++") if shutil.which(c)), None)
if CXX is None:
    raise SystemExit("C++20 compiler required for Vulkan atomic-cache gate")

tree = ast.parse((ROOT / "tools/prepare-vulkan-port.py").read_text())
serializer = None
for statement in tree.body:
    if not isinstance(statement, ast.Assign):
        continue
    if any(isinstance(target, ast.Name) and
           target.id == "vulkan_cache_save_replacement" for target in statement.targets):
        serializer = ast.literal_eval(statement.value)
        break
assert serializer and serializer.count("std::filesystem::rename(staging, filename, rename_error);") == 1

header = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <mutex>
#include <string>
#include <system_error>
#include <thread>
#include <vector>
using u32=std::uint32_t;
template<class... A> void log_sink(const char*, A&&...) {}
#define LOG_ERROR(tag, fmt, ...) log_sink(fmt, ##__VA_ARGS__)
#define LOG_WARNING(tag, fmt, ...) log_sink(fmt, ##__VA_ARGS__)
#define LOG_INFO(tag, fmt, ...) log_sink(fmt, ##__VA_ARGS__)
namespace Common::FS {
std::string PathToUTF8String(const std::filesystem::path& p) {
    return p.string();
}
}
constexpr std::array<char,8> VULKAN_CACHE_MAGIC_NUMBER{'E','D','E','N','C','A','C','H'};
namespace vk {
struct PipelineCache {
    std::string bytes;
    explicit operator bool() const { return !bytes.empty(); }
    void Read(std::size_t* size, void* data) const {
        if (!data) { *size = bytes.size(); return; }
        assert(*size >= bytes.size());
        std::memcpy(data, bytes.data(), bytes.size());
        *size=bytes.size();
    }
};
}
class PipelineCache {
public:
    void SerializeVulkanPipelineCache(const std::filesystem::path&,
                                       const vk::PipelineCache&, u32);
};
"""
main = r"""
std::string read_file(const std::filesystem::path& file) {
    std::ifstream in(file, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>{in},
                       std::istreambuf_iterator<char>{});
}
bool valid_cache(const std::string& bytes) {
    if (bytes.size() < 12) return false;
    return std::memcmp(bytes.data(), VULKAN_CACHE_MAGIC_NUMBER.data(), 8) == 0;
}
int main(int argc, char** argv) {
    assert(argc == 2);
    namespace fs = std::filesystem;
    fs::path target=fs::path(argv[1]) / "pipelines.bin";
    fs::path staging=target;
    staging += ".new";
    PipelineCache cache;
    vk::PipelineCache first{"compiled-driver-pipeline-A"};
    cache.SerializeVulkanPipelineCache(target, first, 42);
    auto original=read_file(target);
    assert(valid_cache(original));
    assert(original.find(first.bytes) != std::string::npos);
    assert(!fs::exists(staging));

    // Force temporary open to fail while preserving a previously valid cache.
    fs::create_directory(staging);
    std::ofstream(staging / "blocker.txt").put('x');
    cache.SerializeVulkanPipelineCache(target, vk::PipelineCache{"new"}, 42);
    assert(read_file(target) == original);
    fs::remove_all(staging);

    // Simulate two background flush requests competing with game exit.
    std::thread one([&] {
        cache.SerializeVulkanPipelineCache(target, vk::PipelineCache{"thread-ONE"}, 42);
    });
    std::thread two([&] {
        cache.SerializeVulkanPipelineCache(target, vk::PipelineCache{"thread-TWO"}, 42);
    });
    one.join();
    two.join();
    const auto final_bytes=read_file(target);
    assert(valid_cache(final_bytes));
    assert(final_bytes.find("thread-ONE") != std::string::npos ||
           final_bytes.find("thread-TWO") != std::string::npos);
    assert(!fs::exists(staging));
}
"""
with tempfile.TemporaryDirectory(prefix="eden-vulkan-atomic-") as tmp:
    directory = Path(tmp)
    source = directory / "cache.cpp"
    executable = directory / "cache"
    source.write_text(header + "\n" + serializer + "\n" + main)
    subprocess.run([CXX, "-std=c++20", "-DPS5_NATIVE=1",
                    "-pthread", "-O1", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable), str(directory)], check=True)
print("PASS real derived PS5 Vulkan serializer: atomic save, write failure, concurrent flush")
print("Real PS5 Vulkan driver and firmware persistence: NOT TESTED")
