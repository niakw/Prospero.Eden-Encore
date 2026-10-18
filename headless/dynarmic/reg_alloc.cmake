# Canonical Dynarmic register allocator: select the two complete maintained
# sources and preserve the original header shadow/include order.
# EDEN_REGALLOC_VERIFY remains enabled for non-native host qualifications.
macro(eden_reg_alloc_sources)
    set(EDEN_MAINTAINED_REGALLOC
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/backend/x64")
    foreach(source IN ITEMS reg_alloc.h reg_alloc.cpp)
        if(NOT EXISTS "${EDEN_MAINTAINED_REGALLOC}/${source}")
            message(FATAL_ERROR "Missing maintained register allocator ${source}")
        endif()
    endforeach()
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/dynarmic/backend/x64")
    configure_file("${EDEN_MAINTAINED_REGALLOC}/reg_alloc.h"
        "${PORT_BUILD_DIR}/include/dynarmic/backend/x64/reg_alloc.h" COPYONLY)
    get_target_property(eden_ra_sources dynarmic SOURCES)
    list(FILTER eden_ra_sources EXCLUDE REGEX "(^|/)backend/x64/reg_alloc\\.cpp$")
    set_property(TARGET dynarmic PROPERTY SOURCES "${eden_ra_sources}")
    target_sources(dynarmic PRIVATE "${EDEN_MAINTAINED_REGALLOC}/reg_alloc.cpp")
    target_compile_definitions(dynarmic PRIVATE EDEN_REGALLOC_TRACKED=1)
    if(NOT PS5_NATIVE)
        target_compile_definitions(dynarmic PRIVATE EDEN_REGALLOC_VERIFY=1)
    endif()
endmacro()
