#!/usr/bin/env python3
"""Host regression for the exact maintained IPC receive loop.

When KSynchronizationObject::Wait returns an error without storing an index,
ReplyAndReceiveImpl must return -1 rather than exposing uninitialized memory.
Tests normal and DEV source-extracted loops with ASan/UBSan; timeout leaves
the caller's index untouched, and successful and NotFound/retry preserve slots.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
directory = root / "vendor/encore-active/eden-core/src/core/hle/kernel/svc"
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/svc/svc_ipc.cpp").read_text()
standard = (directory / "svc_ipc_standard.cpp").read_text()
developer = (directory / "svc_ipc.cpp").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/verify/hle/check-native-hle-ipc-receive-index-host.py" in workflow
def extract(source):
    first = "        // Wait for a message.\n"
    last = "\n    }\n}\n\nResult ReplyAndReceiveImpl("
    assert source.count(first) == 1 and source.count(last) == 1
    return source.split(first, 1)[1].split(last, 1)[0].rstrip()
for source in (standard, developer):
    body = extract(source)
    assert body.count("s32 index{-1};") == 1
    assert "KSynchronizationObject::Wait(kernel, std::addressof(index)" in body
    assert body.index("s32 index{-1};") < body.index("KSynchronizationObject::Wait(")
    assert body.index("if (ResultTimedOut == result)") < body.index("*out_index = index;")
    assert body.index("if (R_SUCCEEDED(result))") < body.index("*out_index = index;")
assert "if (index < 0 || index >= num_objects || objs[index] == nullptr)" in extract(standard)
assert "if (index < 0 || index >= num_objects || objs[index] == nullptr)" not in extract(developer)
assert "s32 index{-1};" not in extract(pinned)

code = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <vector>
using s32 = std::int32_t;
using s64 = std::int64_t;
using Result = std::int32_t;
static constexpr Result ResultSuccess = 0;
static constexpr Result ResultCancelled = 11;
static constexpr Result ResultTimedOut = 12;
static constexpr Result ResultTerminated = 13;
static constexpr Result ResultNotFound = 14;
static constexpr Result ResultOutOfRange = 15;
#define R_SUCCEEDED(value) ((value) == ResultSuccess)
#define R_RETURN(value) return (value)
#define R_THROW(value) return (value)
struct KernelCore {};
struct KServerSession;
struct KSynchronizationObject {
    virtual ~KSynchronizationObject() = default;
    template<class T> T DynamicCast() { return dynamic_cast<T>(this); }
    static Result Wait(KernelCore&, s32*, KSynchronizationObject**, s32, s64);
};
struct KServerSession final : KSynchronizationObject {
    static int receive_calls;
    static Result receive_result;
    Result ReceiveRequest(KernelCore&, std::uintptr_t, std::size_t, std::uint64_t) {
        ++receive_calls;
        return receive_result;
    }
};
int KServerSession::receive_calls = 0;
Result KServerSession::receive_result = ResultSuccess;
static std::vector<Result> results;
static std::size_t next_result = 0;
static s32 simulated_success_index = 0;
Result KSynchronizationObject::Wait(KernelCore&, s32* index,
                                    KSynchronizationObject**, s32, s64) {
    assert(next_result < results.size());
    const auto r = results[next_result++];
    if (r == ResultSuccess) *index = simulated_success_index;
    return r;
}
Result ReplyAndReceive(KernelCore& kernel, s32* out_index,
                       KSynchronizationObject** objs, s32 num_objects, s64 timeout) {
    std::uintptr_t message = 0;
    std::size_t buffer_size = 0;
    std::uint64_t message_paddr = 0;
INJECT
}
static void Scenario(const std::vector<Result>& plan, Result expected,
                     s32 expected_index, Result receive = ResultSuccess,
                     s32 success_index = 0, bool empty_object = false) {
    KernelCore kernel;
    KServerSession session;
    KSynchronizationObject* objects[] = {empty_object ? nullptr : &session};
    simulated_success_index = success_index;
    results = plan;
    next_result = 0;
    KServerSession::receive_calls = 0;
    KServerSession::receive_result = receive;
    s32 index = 777;
    const auto result = ReplyAndReceive(kernel, &index, objects, 1, -1);
    assert(result == expected);
    assert(index == expected_index);
    assert(next_result == plan.size());
}
int main() {
    Scenario({ResultCancelled}, ResultCancelled, -1);
    Scenario({ResultTerminated}, ResultTerminated, -1);
    Scenario({ResultTimedOut}, ResultTimedOut, 777);
    Scenario({ResultSuccess}, ResultSuccess, 0);
    Scenario({ResultSuccess}, ResultNotFound, 0, ResultNotFound);
    // ReceiveRequest's NotFound retries the synchronization wait; a later
    // cancellation returns an unambiguous invalid slot.
    Scenario({ResultSuccess, ResultCancelled}, ResultCancelled, -1, ResultNotFound);
#ifdef EDEN_IPC_STANDARD_SLOT_CHECK
    // The normal native path must refuse impossible success slots before
    // dereferencing objs[index]; DEV deliberately retains its pinned path.
    Scenario({ResultSuccess}, ResultOutOfRange, -1, ResultSuccess, -1);
    Scenario({ResultSuccess}, ResultOutOfRange, -1, ResultSuccess, 1);
    Scenario({ResultSuccess}, ResultOutOfRange, -1, ResultSuccess, 0, true);
#endif
    std::puts("ENCORE_HLE_IPC_INDEX_HOST_PASS");
}
"""
# The NotFound branch loops, so a plan with only success and NotFound
# cannot terminate. Test that error scenario through a two-step plan.
code = code.replace(
    "    Scenario({ResultSuccess}, ResultNotFound, 0, ResultNotFound);\n",
    "")
# R_RETURN macro is used by the extracted C++ loop. Semantics are preserved.
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "A C++20 compiler is required"
with tempfile.TemporaryDirectory(prefix="encore-hle-ipc-index-") as folder:
    folder = Path(folder)
    for name, source in (("standard", standard), ("developer", developer)):
        path = folder / f"{name}.cpp"
        binary = folder / name
        path.write_text(code.replace("INJECT", extract(source)))
        subprocess.run([compiler, "-std=c++20", "-O1", "-pthread", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=address,undefined",
                        "-fno-sanitize-recover=all",
                        *(["-DEDEN_IPC_STANDARD_SLOT_CHECK=1"] if name == "standard" else []),
                        str(path), "-o", str(binary)],
                       check=True, capture_output=True, text=True, timeout=90)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, (name, result.stdout[-1000:], result.stderr[-2000:])
print("NATIVE_HLE_IPC_RECEIVE_INDEX_HOST_PASS source_extracted=2 cancelled=1 termination=1 timeout=1 retry=1 asan_ubsan=1")
