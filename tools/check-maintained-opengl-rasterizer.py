#!/usr/bin/env python3
"""Verify both selected OpenGL rasterizer profiles are equivalent to the retired CMake versions."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/video_core/renderer_opengl/gl_rasterizer.cpp").read_text()
maintained = root / "vendor/encore-active/eden-core/src/video_core/renderer_opengl"
cmake = (root / "headless/CMakeLists.txt").read_text()
old_tail = "        }\n    });\n}\n\nvoid RasterizerOpenGL::DrawIndirect()"
new_tail = "        }\n        static unsigned traced_draws{};\n        if (traced_draws < 3) {\n            ++traced_draws;\n            LOG_INFO(Render_OpenGL, \"EDEN_GUEST_GL_DRAW count={} error={}\", traced_draws, glGetError());\n        }\n    });\n}\n\nvoid RasterizerOpenGL::DrawIndirect()"
assert pinned.count(old_tail) == 1
baseline = pinned.replace(old_tail, new_tail)
assert (maintained / "gl_rasterizer.cpp").read_text() == baseline
dev = "#include \"dev_render_passes.inc\"\n#include \"performance.h\"\n" + baseline
assert dev.count("        static unsigned traced_draws{};") == 1
dev = dev.replace("        static unsigned traced_draws{};", "        CaptureDevelopmentPass();\n        static unsigned traced_draws{};")
draw_sig = "void RasterizerOpenGL::Draw(bool is_indexed, u32 instance_count) {"
assert dev.count(draw_sig) == 1
dev = dev.replace(draw_sig, draw_sig + "\n    ::Eden::Performance::Timer draw_timer(::Eden::Performance::rasterizer_draw);")
assert (maintained / "gl_rasterizer_dev.cpp").read_text() == dev
assert "CaptureDevelopmentPass();" not in baseline
assert "rasterizer_draw" not in baseline
assert 'list(APPEND video_sources "${EDEN_MAINTAINED_GL_RASTERIZER}")' in cmake
assert '"/gl_rasterizer_dev.cpp"' in cmake
assert 'target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/gl_rasterizer.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/renderer_opengl/gl_rasterizer.cpp"' not in cmake
print("MAINTAINED_OPENGL_RASTERIZER_PARITY_PASS normal=1 dev=1 exclusive_profile_selection=1")
