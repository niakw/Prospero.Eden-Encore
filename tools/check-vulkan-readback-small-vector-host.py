#!/usr/bin/env python3
"""Host C++ sanitizer regression for the PS5 Vulkan readback inline staging batch.

The pinned Eden texture cache already includes boost::container::small_vector.
This exercises its actual 16-item small-storage behavior with move-only maps,
the same tuple type as the extracted Vulkan batch snippet; it is not a
PS5 native GPU image readback.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
batch = (root / "headless/vulkan_download_batch.inc").read_text(encoding="utf-8")
generator = (root / "tools/prepare-vulkan-port.py").read_text(encoding="utf-8")
expected = "boost::container::small_vector<std::pair<ImageId, Map>, 16> pending;"
assert expected in batch
assert "std::vector<std::pair<ImageId, Map>> pending;" not in batch
assert "pending.reserve(16);" not in batch
assert "pending.size() == 16" in batch
assert "finish_batch();" in batch
assert "(port / 'vulkan_download_batch.inc').read_text()" in generator

compiler = next((exe for exe in ("clang++-18", "clang++", "g++")
                 if shutil.which(exe)), None)
if compiler is None:
    raise SystemExit("No C++20 compiler; refusing an unexecuted regression PASS")

source = r"""
#include <boost/container/small_vector.hpp>
#include <cassert>
#include <cstddef>
#include <memory>
#include <utility>

struct MoveOnlyMap {
    std::unique_ptr<int> token;
    explicit MoveOnlyMap(int value) : token(std::make_unique<int>(value)) {}
    MoveOnlyMap(MoveOnlyMap&&) noexcept = default;
    MoveOnlyMap& operator=(MoveOnlyMap&&) noexcept = default;
    MoveOnlyMap(const MoveOnlyMap&) = delete;
    MoveOnlyMap& operator=(const MoveOnlyMap&) = delete;
};
int main() {
    using ImageId = unsigned;
    using Map = MoveOnlyMap;
    using Pending = boost::container::small_vector<std::pair<ImageId, Map>, 16>;
    static_assert(Pending::static_capacity == 16);
    Pending pending;
    assert(pending.capacity() >= 16);
    for (int batch = 0; batch < 1000; ++batch) {
        for (unsigned id = 0; id < 16; ++id) {
            assert(pending.size() < 16);
            pending.emplace_back(id, Map{static_cast<int>(id + batch)});
        }
        assert(pending.size() == 16);
        for (auto& [id, map] : pending) {
            assert(map.token);
            assert(*map.token == static_cast<int>(id + batch));
        }
        pending.clear();
        assert(pending.empty());
        assert(pending.capacity() >= 16);
    }
}
"""
with tempfile.TemporaryDirectory(prefix="eden-vulkan-readback-") as folder:
    cpp = Path(folder) / "readback.cpp"
    exe = Path(folder) / "readback"
    cpp.write_text(source, encoding="utf-8")
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", str(cpp), "-o", str(exe)],
                   check=True, timeout=90)
    subprocess.run([str(exe)], check=True, timeout=90)
print("PASS Vulkan host texture readback small_vector: 1000 batches x16 move-only maps under ASan/UBSan")
print("Actual PS5 Vulkan transfer bandwidth and FC27 frame times remain unqualified")
