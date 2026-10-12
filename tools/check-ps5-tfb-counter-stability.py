#!/usr/bin/env python3
"""Guard native PS5 Vulkan transform-feedback counter begin/end symmetry.

This checks the actually vendored Vulkan C++ translation unit AND the
generator's source-to-output replacement. The full fork equivalence gate
independently compares all 40 active Vulkan files to generated sources.
No PS5 compilation, GPU device or gameplay inference.
"""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
active = (root / "vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
base = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_query_cache.cpp").read_text()
begin = active.split("    void FlushBeginTFB() {", 1)[1].split("    void FlushEndTFB() {", 1)[0]
end = active.split("    void FlushEndTFB() {", 1)[1].split("    void UpdateBuffers() {", 1)[0]

assert begin.count("UpdateBuffers();") == 1, "UpdateBuffers must run before BeginTFB"
assert "BeginTransformFeedbackEXT(" in begin
assert "EndTransformFeedbackEXT(" in end
assert end.count("UpdateBuffers();") == 0, "TFB end must preserve begin-time counter count"
assert "has_flushed_end_pending = false;" in end
assert "if (buffers_count == 0)" in end

old = ("        // Refresh buffer state before ending transform feedback to ensure counters_count is up-to-date.\n"
       "        UpdateBuffers();\n")
tree = ast.parse(generator)
found = 0
for node in ast.walk(tree):
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "adapt"):
        continue
    if not node.args or not isinstance(node.args[0], ast.Constant):
        continue
    if node.args[0].value != "src/video_core/renderer_vulkan/vk_query_cache.cpp":
        continue
    assert len(node.args) == 3 and isinstance(node.args[2], ast.List)
    for pair in node.args[2].elts:
        if not isinstance(pair, ast.Tuple) or len(pair.elts) != 2:
            continue
        before, after = pair.elts
        if (isinstance(before, ast.Constant) and before.value == old):
            assert isinstance(after, ast.Constant) and after.value == ""
            found += 1
assert found == 1, "generator must remove exactly the same two lines as active C++"
assert base.count(old) == 1
assert active.count(old) == 0
print("PASS: pinned source has old EndTFB refresh; generator removes it once; compiled fork refreshes only on BeginTFB")
