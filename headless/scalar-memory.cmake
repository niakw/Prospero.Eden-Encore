# Keep scalar SIMD accesses in XMM registers on the checked page-table path.
# Reuse the original scalar callback ABI; its temporary GPR is reserved before
# branching, and all register allocation remains outside deferred callbacks.
foreach(direction Read Write)
    string(TOLOWER "${direction}" lower)
    file(READ "${EDEN_SCALAR_INPUT_DIR}/scalar-memory-${lower}.inc" scalar_access)
    string(FIND "${memory_source}" "void AxxEmitX64::EmitMemory${direction}(" begin)
    if(begin LESS 0)
        message(FATAL_ERROR "Pinned scalar memory emitter changed")
    endif()
    string(SUBSTRING "${memory_source}" 0 ${begin} prefix)
    string(SUBSTRING "${memory_source}" ${begin} -1 body)
    string(FIND "${body}" "    if (ordered && bitsize == 128)" offset)
    if(offset LESS 0)
        message(FATAL_ERROR "Pinned memory callback boundary changed")
    endif()
    string(SUBSTRING "${body}" 0 ${offset} before)
    string(SUBSTRING "${body}" ${offset} -1 after)
    set(memory_source "${prefix}${before}${scalar_access}${after}")
endforeach()

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
