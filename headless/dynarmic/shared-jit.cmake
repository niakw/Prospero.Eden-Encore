# ProsperoEden: one compiled-code namespace per guest process for the A64 JITs
# (headless/dynarmic/jit_group.h). Each macro edits a source already read into the caller's
# variable, just before the caller writes the derived file.

set(EDEN_SHARED_JIT_DIR "${PORT_ROOT}/vendor/encore-active/eden-core/dynarmic/shared-jit")
if(NOT EXISTS "${EDEN_SHARED_JIT_DIR}/jit_group.h")
    message(FATAL_ERROR "Missing Encore-maintained shared JIT code")
endif()
file(GLOB eden_shared_jit_inputs CONFIGURE_DEPENDS "${EDEN_SHARED_JIT_DIR}/*.inc" "${EDEN_SHARED_JIT_DIR}/*.h"
     "${EDEN_SHARED_JIT_DIR}/*.cpp")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${eden_shared_jit_inputs})

function(eden_shared_jit_require source anchor what)
    string(FIND "${source}" "${anchor}" at)
    if(at LESS 0)
        message(FATAL_ERROR "Pinned ${what} changed for the shared JIT")
    endif()
endfunction()

# a64_emit_x64.h: the group and the guest range of the last Emit.
# emit_x64_memory.cpp.inc: the running core's monitor slots and configuration.
macro(eden_shared_jit_memory_inc)
    set(eden_address "code.mov(tmp, std::bit_cast<u64>(GetExclusiveMonitorAddressPointer(conf.global_monitor, conf.processor_id)));")
    set(eden_value "code.mov(tmp, std::bit_cast<u64>(GetExclusiveMonitorValuePointer(conf.global_monitor, conf.processor_id)));")
    set(eden_conf_cast "code.mov(code.ABI_PARAM1, reinterpret_cast<u64>(&conf));")
    set(eden_conf_plain "code.mov(code.ABI_PARAM1, u64(&conf));")
    foreach(anchor eden_address eden_value eden_conf_cast eden_conf_plain)
        eden_shared_jit_require("${memory_source}" "${${anchor}}" "exclusive monitor emission (${anchor})")
    endforeach()
    string(REPLACE "${eden_address}" "EDEN_EXCLUSIVE_ADDRESS(tmp);" memory_source "${memory_source}")
    string(REPLACE "${eden_value}" "EDEN_EXCLUSIVE_VALUE(tmp);" memory_source "${memory_source}")
    string(REPLACE "${eden_conf_cast}" "EDEN_CONF_ARG();" memory_source "${memory_source}")
    string(REPLACE "${eden_conf_plain}" "EDEN_CONF_ARG();" memory_source "${memory_source}")
endmacro()

# emit_x64_memory.h: A64 code may run on any core, so an exclusive store clears every
# reservation of its address (its own included, which the store consumes anyway).
macro(eden_shared_jit_memory_header)
    set(eden_skip_own "        if (processor_index == conf.processor_id) {\n            continue;\n        }")
    eden_shared_jit_require("${memory_emitter}" "${eden_skip_own}" "exclusive reservation clearing")
    string(REPLACE "${eden_skip_own}"
        "        if constexpr (!requires(const UserConfig& c) { c.tpidr_el0; }) {\n            if (processor_index == conf.processor_id) {\n                continue;\n            }\n        }"
        memory_emitter "${memory_emitter}")
endmacro()

# a64_interface.cpp: upstream's Impl replaced by jit_impl.inc, with the group helpers before it.

# The JIT state layout, the group header and the callback argument registry, all compiled for
# every dynarmic object (the definition recompiles objects that saw the upstream layout).
macro(eden_shared_jit_sources)
    set(eden_jitstate_relative "dynarmic/backend/x64/a64_jitstate.h")
    file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/${eden_jitstate_relative}" eden_jitstate)
    set(eden_jitstate_anchor "    std::array<u64, RSB_SIZE> rsb_codeptrs;\n")
    eden_shared_jit_require("${eden_jitstate}" "${eden_jitstate_anchor}" "A64 JIT state")
    string(REPLACE "${eden_jitstate_anchor}" "${eden_jitstate_anchor}
    // ProsperoEden: what generated code reads instead of embedding it, so that any core can run
    // code another core compiled (jit_group.h): this core's callbacks and JIT object, TPIDR
    // registers, exclusive monitor slots, configuration and fast dispatch table.
    void* eden_callbacks = nullptr;
    void* eden_jit = nullptr;
    u64* eden_tpidr_el0 = nullptr;
    const u64* eden_tpidrro_el0 = nullptr;
    void* eden_exclusive_address = nullptr;
    void* eden_exclusive_value = nullptr;
    const void* eden_conf = nullptr;
    void* eden_fast_dispatch = nullptr;
" eden_jitstate "${eden_jitstate}")
    write_derived("${PORT_BUILD_DIR}/include/${eden_jitstate_relative}" "${eden_jitstate}")
    file(READ "${EDEN_SHARED_JIT_DIR}/jit_group.h" eden_group_header)
    write_derived("${PORT_BUILD_DIR}/include/dynarmic/backend/x64/jit_group.h" "${eden_group_header}")
    file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/callback.cpp" eden_callback)
    set(eden_call_arg "    code.mov(code.ABI_PARAM1, arg);\n    code.CallFunction(fn);\n}")
    set(eden_return_arg "    code.mov(code.ABI_PARAM2, arg);\n#endif")
    set(eden_callback_namespace "namespace Dynarmic::Backend::X64 {\n")
    foreach(anchor eden_call_arg eden_return_arg eden_callback_namespace)
        eden_shared_jit_require("${eden_callback}" "${${anchor}}" "callback emission (${anchor})")
    endforeach()
    file(READ "${EDEN_SHARED_JIT_DIR}/jit_state_args.inc" eden_state_args)
    string(REPLACE "${eden_callback_namespace}" "${eden_callback_namespace}${eden_state_args}" eden_callback "${eden_callback}")
    string(REPLACE "${eden_call_arg}" "    EdenLoadArg(code, code.ABI_PARAM1, arg);\n    code.CallFunction(fn);\n}" eden_callback "${eden_callback}")
    string(REPLACE "${eden_return_arg}" "    EdenLoadArg(code, code.ABI_PARAM2, arg);\n#endif" eden_callback "${eden_callback}")
    write_derived("${PORT_BUILD_DIR}/callback.cpp" "#include <array>\n#include <atomic>\n#include <cstdlib>\n#include <optional>\n${eden_callback}")
    get_target_property(eden_jit_sources dynarmic SOURCES)
    list(FILTER eden_jit_sources EXCLUDE REGEX "(^|/)callback\\.cpp$")
    set_property(TARGET dynarmic PROPERTY SOURCES "${eden_jit_sources}")
    target_sources(dynarmic PRIVATE "${PORT_BUILD_DIR}/callback.cpp")
    target_compile_definitions(dynarmic PRIVATE EDEN_SHARED_JIT_LAYOUT=1)
endmacro()
