#!/usr/bin/env python3
"""Host C++ sanitizer regression for the PS5 Vulkan readback inline staging batch.

The pinned Eden texture cache already includes boost::container::small_vector.
This exercises its actual 40-item small-storage behavior with pinned-shape
non-owning staging refs, matching the extracted Vulkan batch snippet; it is
not a PS5 native GPU image readback.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
batch = (root / "headless/vulkan_download_batch.inc").read_text(encoding="utf-8")
generator = (root / "tools/prepare-vulkan-port.py").read_text(encoding="utf-8")
expected = "boost::container::small_vector<std::pair<ImageId, Map>, readback_batch_limit> pending;"
assert expected in batch
assert "constexpr size_t readback_batch_limit = 40;" in batch
assert "std::vector<std::pair<ImageId, Map>> pending;" not in batch
assert "pending.reserve(40);" not in batch
assert "pending.size() == readback_batch_limit" in batch
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
#include <type_traits>
#include <utility>

struct NonOwningMap { int ticket; };
static_assert(std::is_trivially_copyable_v<NonOwningMap>);
int main() {
    using ImageId = unsigned;
    using Map = NonOwningMap;
    using Pending = boost::container::small_vector<std::pair<ImageId, Map>, 40>;
    static_assert(Pending::static_capacity == 40);
    Pending pending;
    assert(pending.capacity() >= 40);
    for (int batch = 0; batch < 1000; ++batch) {
        for (unsigned id = 0; id < 40; ++id) {
            assert(pending.size() < 40);
            pending.emplace_back(id, Map{static_cast<int>(id + batch)});
        }
        assert(pending.size() == 40);
        for (auto& [id, map] : pending) {
            assert(map.ticket == static_cast<int>(id + batch));
        }
        pending.clear();
        assert(pending.empty());
        assert(pending.capacity() >= 40);
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
print("PASS Vulkan host texture readback small_vector: 1000 batches x40 nonowning refs under ASan/UBSan")
print("Actual PS5 Vulkan transfer bandwidth and FC27 frame times remain unqualified")
