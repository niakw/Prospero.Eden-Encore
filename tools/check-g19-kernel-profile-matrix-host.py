#!/usr/bin/env python3
"""G19 kernel shutdown profile oracle (host-only; no console validation)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
legacy = (root / "tools/fixtures/legacy-g19-kernel.cmake").read_text()
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/kernel.cpp" kernel_source)' not in cmake
assert 'write_derived("${PORT_BUILD_DIR}/kernel.cpp"' not in cmake
assert 'list(APPEND core_sources "${EDEN_MAINTAINED_KERNEL_SOURCE}")' in cmake
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/kernel.cpp").read_text()
begin = 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/kernel.cpp" kernel_source)'
finish = 'list(APPEND core_sources "${PORT_BUILD_DIR}/kernel.cpp")\nset_property(TARGET core PROPERTY SOURCES "${core_sources}")'
assert legacy.count(begin) == legacy.count(finish) == 1
start = legacy.index(begin)
end = legacy.index(finish, start) + len(finish)
legacy = legacy[start:end]
selector_start = '# G19: full maintained kernel units; legacy source rewrite is test-only.'
selector_end = 'list(APPEND core_sources "${EDEN_MAINTAINED_KERNEL_SOURCE}")\nset_property(TARGET core PROPERTY SOURCES "${core_sources}")'
assert cmake.count(selector_start) == cmake.count(selector_end) == 1
selection = cmake[cmake.index(selector_start):
                  cmake.index(selector_end, cmake.index(selector_start)) + len(selector_end)]
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
        # CMake validates still-selected pinned units during generation.
        # Only the kernel and server-manager are replaced by the G19 recipe.
        (project / "hle/kernel").mkdir(parents=True)
        (project / "hle/kernel/k_process.cpp").write_text("// stub pinned KProcess for target source resolution\n")
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
        # Validate the CURRENT CMake selector independently of the retired
        # generation fixture, including both upstream side-unit choices.
        select_dir = temp / (name + "-selected")
        select_dir.mkdir()
        select_stage = select_dir / "stage"
        select_stage.mkdir()
        (select_dir / "empty.cpp").write_text("int g19_select_probe() { return 0; }\n")
        (select_dir / "hle/kernel").mkdir(parents=True)
        (select_dir / "hle/kernel/k_process.cpp").write_text("// pinned KProcess stub\n")
        live_header = header.replace(str(stage), str(select_stage))
        (select_dir / "CMakeLists.txt").write_text(
            live_header + selection + '''
get_target_property(g19_selected core SOURCES)
file(WRITE "${PORT_BUILD_DIR}/selected.txt" "${g19_selected}")
''')
        live_result = subprocess.run(
            ["cmake", "-S", str(select_dir), "-B", str(select_dir / "build")],
            capture_output=True, text=True, timeout=60)
        if live_result.returncode:
            print(live_result.stdout[-3000:], live_result.stderr[-5000:])
            raise AssertionError("G19 direct selection failed: " + name)
        live_sources = (select_stage / "selected.txt").read_text().split(";")
        owned_kernel = root / "vendor/encore-active/eden-core/src/core/hle/kernel"/(
            "kernel_dev.cpp" if dev else "kernel_standard.cpp")
        assert live_sources.count(str(owned_kernel)) == 1, name
        assert "hle/kernel/kernel.cpp" not in live_sources
        assert str(stage / "kernel.cpp") not in live_sources
        assert str(select_stage / "kernel.cpp") not in live_sources
        assert "hle/service/server_manager.cpp" not in live_sources
        assert any(p.endswith("/" + server) for p in live_sources), name
        if dev:
            assert any("vendor/encore-active/" in p and p.endswith("/k_process.cpp")
                       for p in live_sources), name
        else:
            assert "hle/kernel/k_process.cpp" in live_sources
        assert owned_kernel.read_text() == unit, name

    # Compare maintained G19 translation units against historical CMake
    # output byte-for-byte; the active selector is migrated only afterwards.
    for name in ("standard", "dev"):
        maintained = root/"vendor/encore-active/eden-core/src/core/hle/kernel"/(
            "kernel_standard.cpp" if name == "standard" else "kernel_dev.cpp")
        assert maintained.read_text() == units[name], "G19 maintained kernel drift " + name
    print("ENCORE_G19_MAINTAINED_KERNEL_PARITY_PASS profiles=2")
    assert units["standard"] != units["dev"]
    assert len(units["dev"]) > len(units["standard"])
print("ENCORE_G19_REAL_CMAKE_PROFILE_MATRIX_PASS profiles=2 selectors=2 native_not_qualified=1")
