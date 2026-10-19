file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/kernel.cpp" kernel_source)
string(REPLACE "    void Shutdown(KernelCore& kernel) {" "    void Shutdown(KernelCore& kernel) {\n        worker_task_manager.WaitForRequests();" kernel_source "${kernel_source}")
string(REPLACE "    ASSERT(R_SUCCEEDED(thread->Run(*this)));\n}"
    "    impl->service_threads.push_back(thread);\n    ASSERT(R_SUCCEEDED(thread->Run(*this)));\n}" kernel_source "${kernel_source}")
string(REPLACE "    std::mutex server_lock;" "    std::vector<KThread*> service_threads;\n    bool services_closing = false;\n    std::mutex server_lock;" kernel_source "${kernel_source}")
string(REPLACE "    void Initialize(KernelCore& kernel) {"
    "    void Initialize(KernelCore& kernel) {\n        services_closing = false;" kernel_source "${kernel_source}")
string(REPLACE "        std::scoped_lock lk{server_lock};\n        server_managers.clear();"
    "        decltype(server_managers) closing_managers;\n        {\n            std::scoped_lock lk{server_lock};\n            services_closing = true;\n            closing_managers.swap(server_managers);\n        }\n        for (auto& manager : closing_managers) manager->RequestStop();\n        closing_managers.clear();\n        for (auto* thread : service_threads) {\n            s32 index;\n            KSynchronizationObject* objects[] = {thread};\n            ASSERT(KSynchronizationObject::Wait(system.Kernel(), &index, objects, 1, -1).IsSuccess());\n            thread->Close(system.Kernel());\n        }\n        service_threads.clear();" kernel_source "${kernel_source}")
if(EDEN_DEV_PROFILE)
    # Development: time the service shutdown phases and every slow manager destruction, named by
    # the service process that ran it.
    string(PREPEND kernel_source "#include <algorithm>\n#include <chrono>\n#include <cstdio>\n#include <string>\n")
    string(REPLACE "    bool services_closing = false;" "    bool services_closing = false;\n    std::vector<std::string> server_names;" kernel_source "${kernel_source}")
    string(REPLACE "            impl->server_managers.emplace_back(std::move(server_manager));\n        }"
        "            impl->server_managers.emplace_back(std::move(server_manager));\n            auto* eden_process = GetCurrentProcessPointer(*this);\n            impl->server_names.emplace_back(eden_process ? eden_process->GetName() : \"?\");\n        }" kernel_source "${kernel_source}")
    string(REPLACE [=[        decltype(server_managers) closing_managers;
        {
            std::scoped_lock lk{server_lock};
            services_closing = true;
            closing_managers.swap(server_managers);
        }
        for (auto& manager : closing_managers) manager->RequestStop();
        closing_managers.clear();
        for (auto* thread : service_threads) {
            s32 index;
            KSynchronizationObject* objects[] = {thread};
            ASSERT(KSynchronizationObject::Wait(system.Kernel(), &index, objects, 1, -1).IsSuccess());
            thread->Close(system.Kernel());
        }
        service_threads.clear();]=] [=[        using EdenClock = std::chrono::steady_clock;
        const auto eden_ms = [](EdenClock::time_point from) {
            return std::chrono::duration<double, std::milli>(EdenClock::now() - from).count();
        };
        const auto eden_start = EdenClock::now();
        decltype(server_managers) closing_managers;
        decltype(server_names) closing_names;
        {
            std::scoped_lock lk{server_lock};
            services_closing = true;
            closing_managers.swap(server_managers);
            closing_names.swap(server_names);
        }
        const double eden_lock_ms = eden_ms(eden_start);
        const size_t eden_count = closing_managers.size();
        auto eden_phase = EdenClock::now();
        double eden_stop_worst = 0;
        for (auto& manager : closing_managers) {
            const auto eden_one = EdenClock::now();
            manager->RequestStop();
            eden_stop_worst = std::max(eden_stop_worst, eden_ms(eden_one));
        }
        const double eden_stop_ms = eden_ms(eden_phase);
        eden_phase = EdenClock::now();
        double eden_worst = 0;
        for (size_t i = 0; i < closing_managers.size(); ++i) {
            const auto eden_one = EdenClock::now();
            closing_managers[i].reset();
            const double ms = eden_ms(eden_one);
            eden_worst = std::max(eden_worst, ms);
            if (ms >= 20.0) {
                std::fprintf(stderr, "EDEN_SHUTDOWN_MANAGER index=%zu name=%s ms=%.1f\n", i,
                             i < closing_names.size() ? closing_names[i].c_str() : "?", ms);
            }
        }
        closing_managers.clear();
        const double eden_destroy_ms = eden_ms(eden_phase);
        eden_phase = EdenClock::now();
        double eden_wait_worst = 0;
        const size_t eden_threads = service_threads.size();
        for (auto* thread : service_threads) {
            const auto eden_one = EdenClock::now();
            s32 index;
            KSynchronizationObject* objects[] = {thread};
            ASSERT(KSynchronizationObject::Wait(system.Kernel(), &index, objects, 1, -1).IsSuccess());
            thread->Close(system.Kernel());
            eden_wait_worst = std::max(eden_wait_worst, eden_ms(eden_one));
        }
        service_threads.clear();
        std::fprintf(stderr, "EDEN_SHUTDOWN_SERVICES managers=%zu threads=%zu lock_ms=%.1f stop_ms=%.1f "
                     "worst_stop_ms=%.1f destroy_ms=%.1f worst_manager_ms=%.1f wait_ms=%.1f "
                     "worst_wait_ms=%.1f total_ms=%.1f\n", eden_count, eden_threads, eden_lock_ms,
                     eden_stop_ms, eden_stop_worst, eden_destroy_ms, eden_worst, eden_ms(eden_phase),
                     eden_wait_worst, eden_ms(eden_start));]=] kernel_source "${kernel_source}")
    # Development: time the kernel teardown steps after the services close (>= 20 ms each), and
    # the cost of an unbuffered stderr line on the console.
    function(eden_patch_kernel match replacement)
        string(FIND "${kernel_source}" "${match}" found_at)
        if(found_at LESS 0)
            message(FATAL_ERROR "Pinned kernel shutdown changed")
        endif()
        string(REPLACE "${match}" "${replacement}" patched "${kernel_source}")
        set(kernel_source "${patched}" PARENT_SCOPE)
    endfunction()
    eden_patch_kernel([=[    void Shutdown(KernelCore& kernel) {
        worker_task_manager.WaitForRequests();]=] [=[    void Shutdown(KernelCore& kernel) {
        auto eden_last = std::chrono::steady_clock::now();
        const auto eden_mark = [&eden_last](const char* step) {
            const auto now = std::chrono::steady_clock::now();
            const double ms = std::chrono::duration<double, std::milli>(now - eden_last).count();
            if (ms >= 20.0) std::fprintf(stderr, "EDEN_SHUTDOWN_KERNEL step=%s ms=%.1f\n", step, ms);
            eden_last = std::chrono::steady_clock::now();
        };
        {
            const auto probe = std::chrono::steady_clock::now();
            for (int line = 0; line < 20; ++line) std::fprintf(stderr, "EDEN_SHUTDOWN_WRITE_PROBE line=%d\n", line);
            std::fprintf(stderr, "EDEN_SHUTDOWN_WRITE_PROBE lines=20 ms=%.1f\n",
                         std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - probe).count());
            eden_last = std::chrono::steady_clock::now();
        }
        worker_task_manager.WaitForRequests();
        eden_mark("worker_tasks");]=])
    eden_patch_kernel([=[        CloseServices();

        if (application_process) {
            application_process->Close(system.Kernel());
            application_process = nullptr;
        }
]=] [=[        CloseServices();
        eden_mark("close_services");

        if (application_process) {
            application_process->Close(system.Kernel());
            application_process = nullptr;
        }
        eden_mark("application_process");
]=])
    eden_patch_kernel([=[        CleanupObject(system_resource_limit);
]=] [=[        CleanupObject(system_resource_limit);
        eden_mark("persistent_objects");
]=])
    eden_patch_kernel([=[            schedulers[core_id].reset();
        }
]=] [=[            schedulers[core_id].reset();
        }
        eden_mark("schedulers");
]=])
    eden_patch_kernel([=[                registered_in_use_objects.clear();
            }
        }
]=] [=[                registered_in_use_objects.clear();
            }
        }
        eden_mark("in_use_objects");
]=])
    eden_patch_kernel([=[        global_object_list_container.reset();
]=] [=[        global_object_list_container.reset();
        eden_mark("object_container");
]=])
    eden_patch_kernel([=[        hardware_timer.reset();
]=] [=[        hardware_timer.reset();
        eden_mark("hardware_timer");
]=])
endif()
if(EDEN_DEV_PROFILE)
    # Select the complete Encore-maintained diagnostic variant of KProcess.
    # The normal profile continues to compile the untouched pinned source.
    set(EDEN_MAINTAINED_DEV_PROCESS
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/kernel/k_process.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_DEV_PROCESS}")
        message(FATAL_ERROR "Missing maintained KProcess shutdown diagnostic source")
    endif()
    get_target_property(process_core_sources core SOURCES)
    list(REMOVE_ITEM process_core_sources hle/kernel/k_process.cpp)
    list(APPEND process_core_sources "${EDEN_MAINTAINED_DEV_PROCESS}")
    set_property(TARGET core PROPERTY SOURCES "${process_core_sources}")
endif()
# Never wait for service fibers while holding their registration mutex. A late
# registration keeps caller ownership, stops, and runs its normal completion path.
string(REPLACE "        if (impl->is_shutting_down) {\n            return;\n        }\n\n        impl->server_managers.emplace_back(std::move(server_manager));"
    "        if (!impl->services_closing && !impl->is_shutting_down) {\n            impl->server_managers.emplace_back(std::move(server_manager));\n        }" kernel_source "${kernel_source}")
string(REPLACE "    manager->LoopProcess();" "    if (server_manager) manager->RequestStop();\n    manager->LoopProcess();" kernel_source "${kernel_source}")
# ServerManager is maintained as exact full C++ sources, with explicit
# normal/DEV selection. Kernel shutdown calls RequestStop on both variants.
set(server_header "core/hle/service/server_manager.h")
set(EDEN_MAINTAINED_SERVER_ROOT
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service")
if(EDEN_DEV_PROFILE)
    set(EDEN_MAINTAINED_SERVER_HEADER "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager_dev.h")
    set(EDEN_MAINTAINED_SERVER_SOURCE "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager_dev.cpp")
else()
    set(EDEN_MAINTAINED_SERVER_HEADER "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager.h")
    set(EDEN_MAINTAINED_SERVER_SOURCE "${EDEN_MAINTAINED_SERVER_ROOT}/server_manager.cpp")
endif()
if(NOT EXISTS "${EDEN_MAINTAINED_SERVER_HEADER}" OR
   NOT EXISTS "${EDEN_MAINTAINED_SERVER_SOURCE}")
    message(FATAL_ERROR "Missing maintained server-manager source/header pair")
endif()
file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/core/hle/service")
file(REMOVE "${PORT_BUILD_DIR}/include/${server_header}.in")
configure_file("${EDEN_MAINTAINED_SERVER_HEADER}"
    "${PORT_BUILD_DIR}/include/${server_header}" COPYONLY)
get_target_property(core_sources core SOURCES)
list(FIND core_sources hle/service/server_manager.cpp eden_server_original)
if(eden_server_original EQUAL -1)
    message(FATAL_ERROR "Pinned server-manager source moved; requalify Encore selector")
endif()
list(REMOVE_ITEM core_sources hle/service/server_manager.cpp)
list(APPEND core_sources "${EDEN_MAINTAINED_SERVER_SOURCE}")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")
foreach(thread main_thread idle_thread)
    string(REPLACE "            KThread::Register(system.Kernel(), ${thread});"
        "            KThread::Register(system.Kernel(), ${thread});\n            system.Kernel().RegisterInUseObject(${thread});" kernel_source "${kernel_source}")
endforeach()
# Shutdown fibers never call ExitThread. Their original array-held reference
# keeps them alive until CPU joins; balance Run()'s additional reference here.
string(REPLACE "    for (auto* thread : impl->shutdown_threads)\n        void(thread->Run(*this));"
    "    for (auto* thread : impl->shutdown_threads) {\n        ASSERT(thread->Run(*this).IsSuccess());\n        thread->Close(*this);\n    }" kernel_source "${kernel_source}")
write_derived("${PORT_BUILD_DIR}/kernel.cpp" "${kernel_source}")
get_target_property(core_sources core SOURCES)
list(REMOVE_ITEM core_sources hle/kernel/kernel.cpp)
list(APPEND core_sources "${PORT_BUILD_DIR}/kernel.cpp")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")
