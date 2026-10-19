#!/usr/bin/env python3
"""G19 kernel shutdown profile oracle (host-only; no console validation)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/kernel.cpp").read_text()
begin = 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/kernel.cpp" kernel_source)'
finish = 'set_property(TARGET core PROPERTY SOURCES "${core_sources}")'
assert cmake.count(begin) == 1
start = cmake.index(begin)
end = cmake.index(finish, start) + len(finish)
legacy = cmake[start:end]
assert legacy.count('write_derived("${PORT_BUILD_DIR}/kernel.cpp" "${kernel_source}")') == 1
assert legacy.count("eden_patch_kernel([=[") == 7
assert pinned.count("    void Shutdown(KernelCore& kernel) {") == 1
with tempfile.TemporaryDirectory(prefix="encore-g19-oracle-") as td:
    temp = Path(td)
    units = {}
    for name, dev in (("standard", False), ("dev", True)):
        project = temp / name
        project.mkdir()
        stage = project / "stage"
        stage.mkdir()
        (project / "empty.cpp").write_text("int g19_probe() { return 0; }\n")
        header = r'''cmake_minimum_required(VERSION 3.24)
project(EncoreG19Oracle LANGUAGES CXX)
set(PORT_ROOT "__ROOT__")
set(PROJECT_SOURCE_DIR "__ROOT__/vendor/sources/eden")
set(PORT_BUILD_DIR "__STAGE__")
set(EDEN_DEV_PROFILE __DEV__)
add_library(core STATIC
    "${CMAKE_CURRENT_SOURCE_DIR}/empty.cpp"
    hle/kernel/kernel.cpp
    hle/kernel/k_process.cpp
    hle/service/server_manager.cpp)
function(write_derived path content)
    file(WRITE "${path}" "${content}")
endfunction()
'''
        header = (header.replace("__ROOT__", str(root))
                        .replace("__STAGE__", str(stage))
                        .replace("__DEV__", "ON" if dev else "OFF"))
        (project / "CMakeLists.txt").write_text(
            header + legacy + '''
get_target_property(g19_selected core SOURCES)
file(WRITE "${PORT_BUILD_DIR}/selected.txt" "${g19_selected}")
''')
        result = subprocess.run(
            ["cmake", "-S", str(project), "-B", str(project / "build")],
            capture_output=True, text=True, timeout=60)
        if result.returncode:
            print(result.stdout[-3000:], result.stderr[-5000:])
            raise AssertionError("G19 CMake profile failed: " + name)
        unit = (stage / "kernel.cpp").read_text()
        selected = (stage / "selected.txt").read_text().split(";")
        assert len(unit) > len(pinned), name
        assert selected.count(str(stage / "kernel.cpp")) == 1, name
        assert "hle/kernel/kernel.cpp" not in selected
        assert "hle/service/server_manager.cpp" not in selected
        server = "server_manager_dev.cpp" if dev else "server_manager.cpp"
        assert any(p.endswith("/" + server) for p in selected), name
        if dev:
            assert any("vendor/encore-active/" in p and p.endswith("/k_process.cpp")
                       for p in selected), name
        else:
            assert "hle/kernel/k_process.cpp" in selected
        for anchor in (
            "worker_task_manager.WaitForRequests();",
            "impl->service_threads.push_back(thread);",
            "closing_managers.swap(server_managers);",
            "services_closing = true;",
            "manager->RequestStop();",
            "RegisterInUseObject(main_thread)",
            "RegisterInUseObject(idle_thread)",
            "thread->Close(*this);",
        ):
            assert anchor in unit, (name, anchor)
        for anchor in ("EDEN_SHUTDOWN_SERVICES", "EDEN_SHUTDOWN_KERNEL",
                       "EDEN_SHUTDOWN_WRITE_PROBE", "eden_mark(", "closing_names"):
            assert (anchor in unit) == dev, (name, anchor)
        units[name] = unit
    assert units["standard"] != units["dev"]
    assert len(units["dev"]) > len(units["standard"])
print("ENCORE_G19_REAL_CMAKE_PROFILE_MATRIX_PASS profiles=2 native_not_qualified=1")
