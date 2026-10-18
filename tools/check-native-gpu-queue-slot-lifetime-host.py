#!/usr/bin/env python3
"""Execute pinned GPU queue slot reuse; reject a skipped moved-from destructor.

The real queue stores preconstructed std::array<T, Capacity> slots. A placement
new over a popped (but still live) slot discards its moved-from destructor.
Host fixture uses a valid move type whose source intentionally retains
shared ownership, proving abandoned resources in the original but not in
the native-derived code. No console run or graphics timing claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
original = (root / "vendor/sources/eden/src/common/bounded_threadsafe_queue.h").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
addon = (root / "vendor/encore-active/eden-core/gpu-injections/gpu_queue_stop_wait.inc").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

construct = "std::construct_at(std::addressof(m_data[pos]), std::forward<Args>(args)...);"
cleanup = "std::destroy_at(std::addressof(m_data[pos]));\n        " + construct
canonical = (root / "vendor/encore-active/eden-gpu/include/common/bounded_threadsafe_queue.h").read_text()
assert original.count(construct) == 1
assert addon.count(construct) == 1
assert "python3 -B tools/check-native-gpu-queue-slot-lifetime-host.py" in workflow

# Mirror the derived native header from the same pinned two original paths,
# with exactly the production replacement. Both enqueue APIs must be fixed.
injected = original.replace(
    "        Emplace<PushMode::Wait>(std::forward<Args>(args)...);\n    }",
    "        Emplace<PushMode::Wait>(std::forward<Args>(args)...);\n    }\n" + addon,
    1)
assert injected.count(construct) == 2
derived = injected.replace(construct, cleanup)
assert derived.count(cleanup) == 2
assert derived.count(construct) == 2
assert canonical == "#include <memory>\\n#include <stop_token>\\n".replace("\\n", "\n") + derived
assert 'write_derived("${PORT_BUILD_DIR}/include/common/bounded_threadsafe_queue.h"' not in cmake

program = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <memory>
#include <stop_token>
#include <thread>
#include <utility>
#include "common/bounded_threadsafe_queue.h"

struct Resource {
    static inline int living{};
    Resource() { ++living; }
    ~Resource() { --living; }
};
struct RetainedAfterMove {
    std::shared_ptr<Resource> payload;
    RetainedAfterMove() = default;
    explicit RetainedAfterMove(const std::shared_ptr<Resource>& resource)
        : payload(resource) {}
    // Valid move operations: the source deliberately keeps an owner.
    RetainedAfterMove(RetainedAfterMove&& other) noexcept
        : payload(other.payload) {}
    RetainedAfterMove& operator=(RetainedAfterMove&& other) noexcept {
        payload = other.payload;
        return *this;
    }
    RetainedAfterMove(const RetainedAfterMove&) = delete;
    RetainedAfterMove& operator=(const RetainedAfterMove&) = delete;
};

int main() {
    {
        Common::SPSCQueue<RetainedAfterMove, 2> q;
        RetainedAfterMove received;
        for (unsigned i = 0; i < 12; ++i) {
            auto resource = std::make_shared<Resource>();
            assert(q.TryEmplace(resource));
            assert(q.TryPop(received));
            assert(received.payload == resource);
            received.payload.reset();
            resource.reset();
        }
#if EXPECT_REPAIRED
        // At most two moved-from slots still hold an owner.
        assert(Resource::living == 2);
#else
        // Baseline has overwritten ten live moved-from owners, leaking each.
        assert(Resource::living == 12);
#endif
    }
#if EXPECT_REPAIRED
    assert(Resource::living == 0);
    std::puts("PINNED_GPU_QUEUE_SLOT_DESTRUCTOR_REUSE_PASS");
#else
    assert(Resource::living == 10);
    std::puts("PINNED_GPU_QUEUE_ORIGINAL_MOVED_FROM_OWNER_LEAK_WITNESS_PASS");
#endif
}
"""
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-native-queue-lifetime-") as folder:
    temp = Path(folder)
    inc = temp / "common"
    inc.mkdir()
    # The upstream polyfill is not involved in the queue slot's semantics.
    (inc / "polyfill_thread.h").write_text("#pragma once\n#include <stop_token>\n")
    code = temp / "queue_lifetime.cpp"
    code.write_text(program)
    for name, source, repaired in (
        ("original", original, False),
        ("derived", derived, True),
    ):
        (inc / "bounded_threadsafe_queue.h").write_text(
            "#include <memory>\n#include <stop_token>\n" + source
        )
        binary = temp / name
        subprocess.run(
            [compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
             "-pthread", "-I", str(temp), "-DEXPECT_REPAIRED=" + str(int(repaired)),
             str(code), "-o", str(binary)], check=True, timeout=30)
        result = subprocess.run([str(binary)], check=True, text=True,
                                capture_output=True, timeout=10)
        print(result.stdout, end="")

print("PINNED_GPU_QUEUE_NATIVE_REPAIR_SCOPE_ONLY")
