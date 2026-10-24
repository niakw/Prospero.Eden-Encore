#!/usr/bin/env python3
"""Compile the selected native feedback-loop function without network access.

The pinned patch-replay test lives in check-ps5-feedback-loop-view-cache.py.
This additional preflight reads the *selected maintained source*, exercising
untextured -> sampled-depth -> untextured -> sampled-depth transitions.
It demonstrates no lost feedback barrier, not a console FPS improvement.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
patch = (root / "headless/backports/eden-ps5-feedback-loop-no-depth-fastpath.patch").read_text()
original_test = (root / "tools/check-ps5-feedback-loop-view-cache.py").read_text()
start = native.index("void TextureCache<P>::CheckFeedbackLoop(")
end = native.index("\ntemplate <class P>", start)
method = native[start:end]
# The shared pinned-source fixture now checks that stable serials compare
# image-view identities while changed serials skip them. This test extracts
# the selected maintained function instead of its instrumented pinned replay,
# so install the SAME counter at the actual view comparison before compiling.
key_compare = "            if (last_feedback_view_ids[i] != views[i].id) {"
assert method.count(key_compare) == 1
assert "inline unsigned view_key_comparisons=0;" in (
    (root / "tools/check-ps5-feedback-loop-view-cache.py").read_text())
method = method.replace(
    key_compare, "            ++view_key_comparisons;\n" + key_compare)

guard = """    // No sampled view can participate in a framebuffer feedback loop.
    // Avoid even the view-key comparison and snapshot for untextured draws.
    if (views.empty()) {
        last_feedback_loop_serial = render_targets_serial;
        last_feedback_texture_serial = texture_bindings_serial;
        last_feedback_loop_result = false;
        last_feedback_view_ids.clear();
        return;
    }
"""
assert method.count(guard) == 1
assert guard in patch.replace("\n+", "\n"), "Native backport and maintained source diverged"
assert method.index("if (views.empty())") < method.index("if ((rt_active_mask & (1u << NUM_RT)) == 0)")
assert method.index("if (views.empty())") < method.index("identical_bound_views")

def get_literal(start_marker: str) -> str:
    assert original_test.count(start_marker) == 1, start_marker
    return original_test.split(start_marker, 1)[1].split('"""', 1)[0]

prologue = get_literal('    prologue=r"""')
epilogue = get_literal('    epilogue=r"""')

# The existing source-extracted test contains a depth->unrelated->depth
# sequence, an empty view set, and a no-depth->depth transition.
assert "tc.CheckFeedbackLoop(std::span<const ImageViewInOut>{});" in epilogue
assert "tc.rt_active_mask=1u<<NUM_RT;" in epilogue
assert "assert(tc.runtime.calls==5);" in epilogue
code = prologue + "\ntemplate<class P>\n" + method + "\n" + epilogue

compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-native-feedback-loop-") as temp:
    cpp = Path(temp) / "feedback.cpp"
    cpp.write_text(code)
    for opt in ("-O0", "-O2"):
        for label, defines in (("native", ["-DPS5_NATIVE"]), ("upstream", [])):
            exe = Path(temp) / (label + opt)
            build = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 *defines, str(cpp), "-o", str(exe)],
                text=True, capture_output=True, timeout=45,
            )
            assert build.returncode == 0, (opt, label, build.stderr[-4000:])
            run = subprocess.run(
                [str(exe)], text=True, capture_output=True, timeout=15,
            )
            assert run.returncode == 0, (opt, label, run.stdout, run.stderr[-4000:])
            print("NATIVE_FEEDBACK_EMPTY_VIEW_PASS", opt, label)
