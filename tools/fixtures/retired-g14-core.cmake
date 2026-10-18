# Archived G14 Core::System transformations -- parity test ONLY.
# Never include this fixture in any production CMake configuration.
function(write_derived path content)
    file(WRITE "${path}" "${content}")
endfunction()
# Load() already resolves the ID into its per-load parameters. Reuse it for
# overrides instead of reading again into an uninitialized persistent field.
file(READ "${PROJECT_SOURCE_DIR}/src/core/core.cpp" system_source)
foreach(header game_settings.h launch_timestamp_cache.h)
    string(REPLACE "#include \"${header}\"" "#include \"core/${header}\"" system_source "${system_source}")
endforeach()
string(REPLACE "    u64 program_id;\n\n" "" system_source "${system_source}")
string(REPLACE "        if (app_loader->ReadProgramId(program_id) != Loader::ResultStatus::Success) {\n            LOG_ERROR(Core, \"Failed to find program id for ROM\");\n        }\n\n" "" system_source "${system_source}")
string(REPLACE "GameSettings::LoadOverrides(program_id," "GameSettings::LoadOverrides(params.program_id," system_source "${system_source}")
# Join callbacks before their service-owned targets can be destroyed.
set(old_audio_shutdown "        stop_event.request_stop();")
string(FIND "${system_source}" "${old_audio_shutdown}" audio_shutdown_offset)
if(audio_shutdown_offset LESS 0)
    message(FATAL_ERROR "Pinned service shutdown changed; review audio callback lifetime.")
endif()
string(REPLACE "${old_audio_shutdown}"
    "        if (audio_core) audio_core->Shutdown();\n${old_audio_shutdown}" system_source "${system_source}")
# Cheat-engine timing callbacks can read HID/services while shutdown advances. Destroy the engine
# before CloseServices() so a stop cannot race a callback against already-torn-down services.
set(old_cheat_shutdown "        kernel.CloseServices();")
string(FIND "${system_source}" "${old_cheat_shutdown}" cheat_shutdown_offset)
if(cheat_shutdown_offset LESS 0)
    message(FATAL_ERROR "Pinned service shutdown changed; review cheat engine lifetime.")
endif()
string(REPLACE "${old_cheat_shutdown}"
    "        cheat_engine.reset();\n${old_cheat_shutdown}" system_source "${system_source}")
# Kernel intrusive lists refer into DeviceMemory even during failed Load unwind.
# Declare the backing first so reverse member destruction releases it last.
string(REPLACE "    std::optional<Core::DeviceMemory> device_memory;\n" "" system_source "${system_source}")
string(REPLACE "    Kernel::KernelCore kernel;"
    "    std::optional<Core::DeviceMemory> device_memory;\n    Kernel::KernelCore kernel;" system_source "${system_source}")
if(PS5_NATIVE)
    foreach(stage "gpu_core->NotifyShutdown();" "if (audio_core) audio_core->Shutdown();" "kernel.SuspendEmulation(true);" "kernel.CloseServices();" "kernel.ShutdownCores();" "services.reset();" "gpu_core.reset();" "cpu_manager.Shutdown();" "kernel.Shutdown();")
        string(REPLACE ";" "" stage_label "${stage}")
        string(REPLACE "${stage}" "${stage}\n        ::Eden::ReportStep(\"shutdown\", \"Completed ${stage_label}\");" system_source "${system_source}")
    endforeach()
    string(PREPEND system_source "#include \"${EDEN_PORT_DIR}/diagnostics.h\"\n")
endif()
# Failed Load still owns a Process wrapper whose destructor touches the kernel.
# Destroy it before kernel.Shutdown tears down its mutexes (both failure paths).
string(REPLACE "            ShutdownMainProcess();\n            return"
    "            process.reset();\n            ShutdownMainProcess();\n            return"
    system_source "${system_source}")
write_derived("${PORT_BUILD_DIR}/core.cpp" "${system_source}")
