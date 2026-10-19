#!/usr/bin/env python3
"""Host-only G21 source matrix: replay the real CMake GPU derivative.

This is a migration oracle, not graphics compilation or hardware qualification.
After G21 is retired, keep its historical recipe as a test-only fixture and
compare maintained translation units byte-for-byte in this same matrix.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
upstream = (root / "vendor/sources/eden/src/video_core/gpu.cpp").read_text()
begin = 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/gpu.cpp" gpu_source)'
finish = 'list(APPEND video_sources "${PORT_BUILD_DIR}/gpu.cpp")'
assert cmake.count(begin) == cmake.count(finish) == 1
body = begin + cmake.split(begin, 1)[1].split(finish, 1)[0] + finish
assert body.count('write_derived("${PORT_BUILD_DIR}/gpu.cpp" "${gpu_source}")') == 1
assert upstream.count("GPU::~GPU() = default;") == 1

profiles = (
    ("gl_host", True, False, False),
    ("gl_host_dev", True, False, True),
    ("gl_native", True, True, False),
    ("gl_native_dev", True, True, True),
    ("vulkan_native", False, True, False),
    ("vulkan_native_dev", False, True, True),
)
results = {}
with tempfile.TemporaryDirectory(prefix="encore-g21-matrix-") as temporary:
    temp = Path(temporary)
    for name, gl, native, dev in profiles:
        directory = temp / name
        stage = directory / "stage"
        directory.mkdir()
        stage.mkdir()
        (directory / "empty.cpp").write_text("int g21_host_fixture() { return 0; }\n")
        prelude = """cmake_minimum_required(VERSION 3.24)
project(EncoreG21Matrix LANGUAGES CXX)
set(PORT_ROOT "__ROOT__")
set(PROJECT_SOURCE_DIR "__ROOT__/vendor/sources/eden")
set(EDEN_PORT_DIR "__ROOT__/headless")
set(PORT_BUILD_DIR "__STAGE__")
set(EDEN_PS5_OPENGL __GL__)
set(PS5_NATIVE __NATIVE__)
set(EDEN_DEV_PROFILE __DEV__)
add_library(video_core STATIC "${CMAKE_CURRENT_SOURCE_DIR}/empty.cpp")
set(video_sources gpu.cpp gpu_thread.cpp dma_pusher.cpp engines/puller.cpp
    renderer_opengl/gl_buffer_cache.cpp renderer_opengl/gl_query_cache.cpp
    renderer_opengl/gl_texture_cache.cpp renderer_opengl/gl_rasterizer.cpp)
function(write_derived path content)
    file(WRITE "${path}.in" "${content}")
    configure_file("${path}.in" "${path}" COPYONLY)
endfunction()
"""
        prelude = (prelude.replace("__ROOT__", str(root))
                          .replace("__STAGE__", str(stage))
                          .replace("__GL__", "ON" if gl else "OFF")
                          .replace("__NATIVE__", "ON" if native else "OFF")
                          .replace("__DEV__", "ON" if dev else "OFF"))
        (directory / "CMakeLists.txt").write_text(prelude + body + "\n")
        result = subprocess.run(
            ["cmake", "-S", str(directory), "-B", str(directory / "build")],
            capture_output=True, text=True, timeout=45)
        if result.returncode:
            print(result.stdout[-2500:], result.stderr[-3500:])
            raise AssertionError("G21 CMake generation failed: " + name)
        actual = (stage / "gpu.cpp").read_text()
        assert len(actual) >= len(upstream) - 2048, (name, len(actual))
        assert actual.count("VideoCommon::GPUThread::ThreadManager gpu_thread;") == 1, name
        if gl:
            assert "RequestSyncOperation([this, &raster_area]()" not in actual, name
            assert "GPU::~GPU() { impl->NotifyShutdown(); }" in actual, name
            assert "RequestSyncOperation([this, raster_area]()" in actual, name
            assert "sync_requests_stopped" in actual, name
            assert "std::rethrow_exception(failure);" in actual, name
            assert "gpu_thread.Stop();" in actual, name
            assert "sync_requests.emplace_back(std::forward<Func>(action));" in actual, name
            assert "lck.unlock();" in actual and "lck.lock();" in actual, name
            assert ('#include <glad/glad.h>' in actual) == native, name
            assert ("::Eden::Performance::BootTrace()" in actual) == dev, name
        else:
            assert "RequestSyncOperation([this, &raster_area]()" in actual, name
            assert "GPU::~GPU() = default;" in actual, name
            assert '#include <glad/glad.h>' not in actual, name
            assert "::Eden::Performance::BootTrace()" not in actual, name
        results[name] = actual
assert results["gl_host"] != results["gl_native"]
assert results["gl_host"] != results["gl_host_dev"]
assert results["gl_native"] != results["gl_native_dev"]
assert results["vulkan_native"] == results["vulkan_native_dev"]
assert results["vulkan_native"] != results["gl_native"]
print("ENCORE_G21_REAL_CMAKE_PROFILE_MATRIX_PASS cases=6 variant_owners=5 host_only=1")
