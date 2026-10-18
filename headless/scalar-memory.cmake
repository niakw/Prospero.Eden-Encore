# Scalar SIMD access bodies reside in the maintained memory method units.
# The two scalar vector/data-processing translation units are complete
# maintained sources. Keep only the memory_source callback transformations
# above pending the separate memory emitter migration.
set(EDEN_MAINTAINED_SCALAR_BACKEND
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/backend/x64")
foreach(unit vector data_processing)
    if(NOT EXISTS "${EDEN_MAINTAINED_SCALAR_BACKEND}/emit_x64_${unit}.cpp")
        message(FATAL_ERROR "Missing maintained scalar emitter ${unit}")
    endif()
endforeach()
get_target_property(jit_sources dynarmic SOURCES)
foreach(unit vector data_processing)
    list(FILTER jit_sources EXCLUDE REGEX "(^|/)emit_x64_${unit}\\.cpp$")
    list(APPEND jit_sources "${EDEN_MAINTAINED_SCALAR_BACKEND}/emit_x64_${unit}.cpp")
endforeach()
set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
