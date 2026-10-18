#!/usr/bin/env python3
"""Exact normal/DEV parity and unique source selection for retired G17/G18."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
pinned = root / "vendor/sources/eden/src/core/hle/service"
active = root / "vendor/encore-active/eden-core/src/core/hle/service"
cmake = (root / "headless/CMakeLists.txt").read_text()
def once(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, ("pinned input changed", old[:80])
    return source.replace(old, new)
header = once((pinned / "server_manager.h").read_text(), "    Result LoopProcess();", "    void RequestStop();\n    Result LoopProcess();")
header_dev = once(header, "    Mutex m_selection_mutex;", "    Mutex m_selection_mutex;\n    std::string m_eden_names;")
assert (active / "server_manager.h").read_text() == header
assert (active / "server_manager_dev.h").read_text() == header_dev
before = "ServerManager::~ServerManager() {\n    // Signal stop.\n    m_stop_source.request_stop();\n    m_wakeup_event->Signal(m_system.Kernel());"
after = "void ServerManager::RequestStop() {\n    m_stop_source.request_stop();\n    m_wakeup_event->Signal(m_system.Kernel());\n}\n\nServerManager::~ServerManager() {\n    RequestStop();"
server = once((pinned / "server_manager.cpp").read_text(), before, after)
server_dev = "#include <chrono>\n#include <cstdio>\n" + server
patches = [["    // Add the new server to sm: and get the moved server port.\n    Kernel::KServerPort* server_port{};","    // Add the new server to sm: and get the moved server port.\n    Kernel::KServerPort* server_port{};\n    m_eden_names += service_name + \" \";"],["    // Create a new port.\n    auto* port = Kernel::KPort::Create(m_system.Kernel());","    // Create a new port.\n    auto* port = Kernel::KPort::Create(m_system.Kernel());\n    m_eden_names += service_name + \" \";"],["ServerManager::~ServerManager() {\n    RequestStop();","ServerManager::~ServerManager() {\n    RequestStop();\n    const auto eden_t0 = std::chrono::steady_clock::now();"],["    m_stopped.Wait();\n    m_threads.clear();","    m_stopped.Wait();\n    const auto eden_t1 = std::chrono::steady_clock::now();\n    m_threads.clear();\n    const auto eden_t2 = std::chrono::steady_clock::now();"],["    // Clean up sessions.","    const auto eden_t3 = std::chrono::steady_clock::now();\n    size_t eden_sessions = 0;\n    // Clean up sessions."],["        delete session;\n    }\n\n    // Close wakeup event.","        delete session;\n        ++eden_sessions;\n    }\n    const auto eden_t4 = std::chrono::steady_clock::now();\n\n    // Close wakeup event."],["        // Write event is owned by ServiceManager\n    }\n}","        // Write event is owned by ServiceManager\n    }\n    const auto eden_t5 = std::chrono::steady_clock::now();\n    const auto eden_span = [](auto a, auto b) { return std::chrono::duration<double, std::milli>(b - a).count(); };\n    if (eden_span(eden_t0, eden_t5) >= 10.0) {\n        std::fprintf(stderr, \"EDEN_SHUTDOWN_DTOR manager=%p services=%s stopped=%.1f threads=%.1f ports=%.1f sessions=%.1f n=%zu events=%.1f\\n\",\n                     static_cast<void*>(this), m_eden_names.c_str(), eden_span(eden_t0, eden_t1), eden_span(eden_t1, eden_t2),\n                     eden_span(eden_t2, eden_t3), eden_span(eden_t3, eden_t4), eden_sessions, eden_span(eden_t4, eden_t5));\n    }\n}"]]
assert len(patches) == 7
for original, replacement in patches:
    server_dev = once(server_dev, original, replacement)
assert (active / "server_manager.cpp").read_text() == server
assert (active / "server_manager_dev.cpp").read_text() == server_dev
assert "EDEN_SHUTDOWN_DTOR" in server_dev
assert "EDEN_SHUTDOWN_DTOR" not in server
assert cmake.count('configure_file("${EDEN_MAINTAINED_SERVER_HEADER}"') == 1
assert cmake.count('list(APPEND core_sources "${EDEN_MAINTAINED_SERVER_SOURCE}")') == 1
assert cmake.count('list(REMOVE_ITEM core_sources hle/service/server_manager.cpp)') == 1
assert 'set(EDEN_MAINTAINED_SERVER_HEADER "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager_dev.h")' in cmake
assert 'set(EDEN_MAINTAINED_SERVER_SOURCE "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager_dev.cpp")' in cmake
assert 'set(EDEN_MAINTAINED_SERVER_HEADER "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager.h")' in cmake
assert 'set(EDEN_MAINTAINED_SERVER_SOURCE "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager.cpp")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/include/${server_header}"' not in cmake
assert 'write_derived("${PORT_BUILD_DIR}/server_manager.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/service/server_manager.cpp"' not in cmake
print("ENCORE_SERVER_MANAGER_PARITY_PASS G17=retired G18=retired variants=2")
