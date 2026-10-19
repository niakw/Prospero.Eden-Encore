# Experimental cross-core JIT: all state, callback and group units come from
# complete maintained Encore sources. No C++ is reconstructed by CMake.

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
# The shared memory header policy is now inside Encore's maintained header.

# a64_interface.cpp: upstream's Impl replaced by jit_impl.inc, with the group helpers before it.

# The JIT state layout, the group header and the callback argument registry, all compiled for
# every dynarmic object (the definition recompiles objects that saw the upstream layout).
macro(eden_shared_jit_sources)
    set(eden_jitstate_relative "dynarmic/backend/x64/a64_jitstate.h")
    # M01 retired: canonical complete A64JitState matches the old derived output.
    if(NOT EXISTS "${EDEN_SHARED_JIT_DIR}/a64_jitstate.h")
        message(FATAL_ERROR "Missing Encore-maintained shared JIT state layout")
    endif()
    configure_file("${EDEN_SHARED_JIT_DIR}/a64_jitstate.h"
        "${PORT_BUILD_DIR}/include/${eden_jitstate_relative}" COPYONLY)
    # M02 retired: the canonical header is already maintained in encore-active.
    # COPYONLY preserves its exact bytes without a second generated source.
    configure_file("${EDEN_SHARED_JIT_DIR}/jit_group.h"
        "${PORT_BUILD_DIR}/include/dynarmic/backend/x64/jit_group.h" COPYONLY)
    # M03 retired: compile the tracked full callback unit, not CMake edits.
    if(NOT EXISTS "${EDEN_SHARED_JIT_DIR}/callback.cpp")
        message(FATAL_ERROR "Missing Encore-maintained shared JIT callback unit")
    endif()
    configure_file("${EDEN_SHARED_JIT_DIR}/callback.cpp"
        "${PORT_BUILD_DIR}/callback.cpp" COPYONLY)
    get_target_property(eden_jit_sources dynarmic SOURCES)
    list(FILTER eden_jit_sources EXCLUDE REGEX "(^|/)callback\\.cpp$")
    set_property(TARGET dynarmic PROPERTY SOURCES "${eden_jit_sources}")
    target_sources(dynarmic PRIVATE "${PORT_BUILD_DIR}/callback.cpp")
    target_compile_definitions(dynarmic PRIVATE EDEN_SHARED_JIT_LAYOUT=1)
endmacro()
