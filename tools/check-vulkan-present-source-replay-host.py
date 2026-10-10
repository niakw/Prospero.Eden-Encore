#!/usr/bin/env python3
"""Replay the ACTUAL PS5 Vulkan present-manager generator edits on pinned upstream.

Unlike string-only/mocked-gate checks, fetch both whole Eden source files
identified by verified Git blob IDs and apply the *production* adapt() tuples
in their real sequential order. This is a source-generation integration check,
NOT a native PS5/Vulkan driver compile or 13.60 firmware runtime test.
"""
import ast
import hashlib
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
pinned = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
expected_blobs = {
    "src/video_core/renderer_vulkan/vk_present_manager.cpp":
        "3491f8fb7563f2557a476fec8edb4f220f5d27fc",
    "src/video_core/renderer_vulkan/vk_present_manager.h":
        "577a82098aba7d65060c7ccda0d50aef81b77c3d",
}
tree = ast.parse((root / "tools/prepare-vulkan-port.py").read_text())
adapters = {}
for node in tree.body:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        continue
    call = node.value
    if not isinstance(call.func, ast.Name) or call.func.id != "adapt":
        continue
    if len(call.args) != 3 or not isinstance(call.args[0], ast.Constant):
        continue
    relative = call.args[0].value
    if relative not in expected_blobs:
        continue
    assert relative not in adapters, "Duplicate pinned adaptation: " + relative
    target = ast.literal_eval(call.args[1])
    replacements = ast.literal_eval(call.args[2])
    assert all(isinstance(x, tuple) and len(x) == 2 for x in replacements)
    adapters[relative] = (target, replacements)
assert set(adapters) == set(expected_blobs), "Missing production Vulkan present adapter"

rendered = {}
for path, expected_sha in expected_blobs.items():
    url = f"https://raw.githubusercontent.com/eden-emulator/mirror/{pinned}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "EdenEncore-SourceReplay/1"})
    with urllib.request.urlopen(request, timeout=35) as response:
        data = response.read()
    blob_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert blob_sha == expected_sha, f"Pinned upstream blob drift: {path}: {blob_sha}"
    source = data.decode("utf-8")
    target, replacements = adapters[path]
    assert target.endswith("vk_present_manager.cpp") or target.endswith("vk_present_manager.h")
    for index, (old, replacement) in enumerate(replacements):
        hits = source.count(old)
        assert hits == 1, f"PS5 generator replacement {index} failed: {path} ({hits} matches): {old[:65]!r}"
        source = source.replace(old, replacement)
    rendered[path] = source

header = rendered["src/video_core/renderer_vulkan/vk_present_manager.h"]
source = rendered["src/video_core/renderer_vulkan/vk_present_manager.cpp"]
assert "bool present_in_flight{}; // guarded by queue_mutex" in header
assert "#include <exception>" in header
assert "std::exception_ptr present_failure;" in header
assert "if (present_failure) std::rethrow_exception(present_failure);" in source
assert source.count("if (present_failure) std::rethrow_exception(present_failure);") == 2
get_frame = source.split("Frame* PresentManager::GetRenderFrame() {", 1)[1].split(
    "void PresentManager::Present(", 1)[0]
pop = get_frame.index("free_queue.pop_front();")
unlock = get_frame.index("lock.unlock();")
fence_wait = get_frame.index("frame->present_done.Wait();")
fence_reset = get_frame.index("frame->present_done.Reset();")
assert pop < unlock < fence_wait < fence_reset
assert get_frame.count("lock.unlock();") == 1
assert "free_cv.wait(lock, [this] { return present_failure || !free_queue.empty(); });" in get_frame
wait_present = source.split("void PresentManager::WaitPresent() {", 1)[1].split(
    "void PresentManager::PresentThread(", 1)[0]
assert "(present_queue.empty() && !present_in_flight)" in wait_present
assert wait_present.index("if (present_failure) std::rethrow_exception(present_failure);") < (
    wait_present.index("std::scoped_lock swapchain_lock{swapchain_mutex};")
)
worker = source.split("void PresentManager::PresentThread(", 1)[1].split(
    "void PresentManager::RecreateSwapchain(", 1)[0]
assert worker.index("present_queue.pop_front();") < worker.index("present_in_flight = true;")
assert worker.index("present_in_flight = true;") < worker.index("CopyToSwapchain(frame);")
assert worker.index("CopyToSwapchain(frame);") < worker.index("free_queue.push_back(frame);")
assert worker.index("free_queue.push_back(frame);") < worker.index("lock.unlock();")
assert worker.index("lock.unlock();") < worker.index("std::lock_guard queue_lock{queue_mutex};")
assert worker.index("std::lock_guard queue_lock{queue_mutex};") < worker.index(
    "present_in_flight = false;")
assert worker.index("present_in_flight = false;") < worker.index("frame_cv.notify_all();")
assert "void(std::exchange(lock, std::unique_lock{swapchain_mutex}));" in worker
assert worker.count("present_in_flight = true;") == 1
assert worker.count("present_in_flight = false;") == 1
assert "std::scoped_lock lock{queue_mutex, free_mutex};" in source
assert "present_queue.clear();\n                present_in_flight = false;" in source
assert "Eden::RecordGpuFailure(error);" in source
print("VULKAN_PRESENT_SOURCE_REPLAY_PASS: 2 pinned source blobs, exact generator edits,")
print("  queue completion, real free-queue unlock, exception publication and wait ordering")
print("Native Vulkan C++ compile, RADV and firmware 13.60 still unverified")
