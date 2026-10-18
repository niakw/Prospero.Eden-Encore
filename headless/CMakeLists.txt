option(EDEN_PS5_VULKAN "Build the native Vulkan renderer alongside OpenGL" OFF)
set(EDEN_VULKAN_DRIVER "CUSTOM" CACHE STRING "Native Vulkan driver: CUSTOM or RADV")
set_property(CACHE EDEN_VULKAN_DRIVER PROPERTY STRINGS CUSTOM RADV)
if(NOT EDEN_VULKAN_DRIVER MATCHES "^(CUSTOM|RADV)$")
    message(FATAL_ERROR "EDEN_VULKAN_DRIVER must be CUSTOM or RADV")
endif()
set(PORT_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(PORT_BUILD_DIR "${CMAKE_BINARY_DIR}/headless")
# Scalar-memory source fragments still consumed by modules trigger configure.
set(EDEN_SCALAR_INPUT_DIR
    "${PORT_ROOT}/vendor/encore-active/eden-core/dynarmic/scalar")
set(EDEN_SCALAR_INPUTS
    "${EDEN_SCALAR_INPUT_DIR}/scalar-memory-read.inc"
    "${EDEN_SCALAR_INPUT_DIR}/scalar-memory-write.inc")
foreach(EDEN_SCALAR_SOURCE IN LISTS EDEN_SCALAR_INPUTS)
    if(NOT EXISTS "${EDEN_SCALAR_SOURCE}")
        message(FATAL_ERROR "Missing Encore-maintained scalar source ${EDEN_SCALAR_SOURCE}")
    endif()
endforeach()
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${EDEN_SCALAR_INPUTS})
# Stability defaults: use Dynarmic's ordinary per-core JIT in production. The cross-core
# JitGroup and bounded successor compile batching are Encore experiments and stay compile-time
# off unless a development build explicitly opts in.
option(EDEN_SHARED_JIT "Enable the experimental cross-core A64 JIT" OFF)
option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)
# Incomplete PS5 sparse JIT page mapper; never expose to normal builds via JSON alone.
option(EDEN_SPARSE_JIT_DEV "Allow developer-only PS5 sparse JIT cache experiments" OFF)
if(EDEN_SPARSE_JIT_DEV AND NOT PS5_NATIVE)
    message(FATAL_ERROR "EDEN_SPARSE_JIT_DEV requires PS5_NATIVE")
endif()
include("${CMAKE_CURRENT_LIST_DIR}/dynarmic/shared-jit.cmake")
# Register-allocator bookkeeping visits only the host locations in use (compile time).
include("${CMAKE_CURRENT_LIST_DIR}/dynarmic/reg_alloc.cmake")
file(MAKE_DIRECTORY "${PORT_BUILD_DIR}")
# SlotVector's throwing-constructor repair has one tracked implementation.
# Use a narrow header-only root to avoid shadowing unrelated pinned includes.
set(EDEN_MAINTAINED_SLOT_VECTOR_ROOT
    "${PORT_ROOT}/vendor/encore-active/eden-core/overrides/slot-vector")
if(NOT EXISTS "${EDEN_MAINTAINED_SLOT_VECTOR_ROOT}/common/slot_vector.h")
    message(FATAL_ERROR "Missing maintained native SlotVector header")
endif()
file(REMOVE "${PORT_BUILD_DIR}/include/common/slot_vector.h")
target_include_directories(common BEFORE PUBLIC "${EDEN_MAINTAINED_SLOT_VECTOR_ROOT}")
target_include_directories(video_core BEFORE PRIVATE "${EDEN_MAINTAINED_SLOT_VECTOR_ROOT}")
file(GLOB overlay_inputs CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/*.inc")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${overlay_inputs})
function(write_derived path content)
    # Preserve timestamps when an overlay is unchanged; otherwise every
    # configure needlessly recompiles hundreds of dependent source files.
    file(WRITE "${path}.in" "${content}")
    configure_file("${path}.in" "${path}" COPYONLY)
endfunction()
# R437: the shipping BufferCache backport is adapted in a single maintained header.
# This only copies tracked bytes into the native include overlay.
if(PS5_NATIVE)
    set(EDEN_MAINTAINED_BUFFER_PAGES
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h")
    if(NOT EXISTS "${EDEN_MAINTAINED_BUFFER_PAGES}")
        message(FATAL_ERROR "Missing maintained R437 BufferCache header")
    endif()
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/buffer-pages/video_core/buffer_cache")
    configure_file("${EDEN_MAINTAINED_BUFFER_PAGES}"
        "${PORT_BUILD_DIR}/buffer-pages/video_core/buffer_cache/buffer_cache.h" COPYONLY)
    target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/buffer-pages" "${EDEN_PORT_DIR}")
endif()
# The texture-cache small-vector Boost version dependency is a complete
# tracked header under vendor/encore-active, not a configure-time replacement.
# Its only modification to the original is #include <boost/version.hpp>.
set(EDEN_SMALL_VECTOR_ROOT "${PORT_ROOT}/vendor/encore-active/eden-core/src")
if(NOT EXISTS "${EDEN_SMALL_VECTOR_ROOT}/video_core/texture_cache/util.h")
    message(FATAL_ERROR "Missing maintained texture-cache type header")
endif()
target_include_directories(video_core BEFORE PRIVATE "${EDEN_SMALL_VECTOR_ROOT}")
# R428: upstream d7f2764 — repeated guest faults must not force a
# synchronous PS5 storage flush for every error line. Keep regular buffer
# flushes and the explicit Flush() API; only coalesce bursts to 100 ms.
# Never edit the immutable Eden logging.cpp source.
set(EDEN_MAINTAINED_LOGGING "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/logging.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_LOGGING}")
    message(FATAL_ERROR "Missing maintained bounded logging source")
endif()
get_target_property(eden_common_sources common SOURCES)
list(FIND eden_common_sources "logging.cpp" eden_pinned_logging_idx)
if(eden_pinned_logging_idx EQUAL -1)
    message(FATAL_ERROR "Pinned logging source moved; requalify maintained overlay")
endif()
list(REMOVE_ITEM eden_common_sources "logging.cpp")
list(APPEND eden_common_sources "${EDEN_MAINTAINED_LOGGING}")
set_property(TARGET common PROPERTY SOURCES "${eden_common_sources}")
# Maintained HLE source selection lives with its code, not in this launcher.
option(EDEN_BLOCKING_GUEST_CONTEXT_LOCKS
    "Use the paired upstream guest scheduler lock fixes" ON)
include("${PORT_ROOT}/vendor/encore-active/eden-threading/native-hle-overrides.cmake")

# The full JIT assertion header is versioned under vendor/encore-active.
# It is byte-equivalent to the previous pinned header + guarded override;
# only the Dynarmic target sees these exceptional-path assertion semantics.
set(EDEN_JIT_ASSERT_ROOT "${PORT_ROOT}/vendor/encore-active/eden-core/src")
if(NOT EXISTS "${EDEN_JIT_ASSERT_ROOT}/common/assert.h")
    message(FATAL_ERROR "Missing maintained JIT assertions")
endif()
target_include_directories(dynarmic BEFORE PRIVATE "${EDEN_JIT_ASSERT_ROOT}")
# Let the existing compiler inline across the JIT's translation units. Keep the
# rest of the native application on its qualified non-LTO build path.
target_compile_options(dynarmic PRIVATE -flto=thin)
if(PS5_NATIVE)
    # Limit ThinLTO and Zen2 tuning to the GPU code; preserve core/common fiber behavior.
    target_compile_options(video_core PRIVATE -flto=thin -march=znver2)
endif()
if(NOT PS5_NATIVE)
    target_link_options(dynarmic INTERFACE -fuse-ld=lld-18)
endif()

# Clang 18 does not accept the upstream GCC TLS-dialect flag. Use the same
# compiler-rt emulated TLS configuration already qualified by G6 on PS5.
# Linux must match its system libstdc++'s native TLS ABI.
foreach(eden_target common core audio_core video_core hid_core network input_common frontend_common shader_recompiler gpu_logging dynarmic)
    if(TARGET ${eden_target})
        get_target_property(options ${eden_target} COMPILE_OPTIONS)
        if(options)
            list(FILTER options EXCLUDE REGEX "mtls-dialect")
            set_property(TARGET ${eden_target} PROPERTY COMPILE_OPTIONS "${options}")
        endif()
        if(PS5_NATIVE)
            target_compile_options(${eden_target} PRIVATE -femulated-tls)
        endif()
    endif()
endforeach()
if(PS5_NATIVE)
    set(COMPILER_RT "${PORT_ROOT}/.deps/compiler-rt-18.1.8")
    # Versioned compiler-rt native TLS runtime; no CMake source mutation.
    set(EDEN_MAINTAINED_EMUTLS
        "${PORT_ROOT}/vendor/encore-active/compiler-rt/emutls.c")
    if(NOT EXISTS "${EDEN_MAINTAINED_EMUTLS}")
        message(FATAL_ERROR "Missing maintained emulated TLS implementation")
    endif()
    target_sources(common PRIVATE "${EDEN_MAINTAINED_EMUTLS}" "${COMPILER_RT}/cpu_model_x86.c")
    target_include_directories(common PRIVATE "${COMPILER_RT}")
    # RADV's AMD addrlib uses __builtin_cpu_supports(), whose x86 runtime
    # state (__cpu_model/__cpu_features2) lives in compiler-rt. Linux CI gets
    # that from Clang's builtins archive; macOS cross-builds provide the same
    # pinned LLVM 18.1.8 implementation directly so the PS5 binary is identical
    # in semantics and does not depend on a host-Linux runtime archive.
    set_source_files_properties("${COMPILER_RT}/cpu_model_x86.c" PROPERTIES
        COMPILE_OPTIONS "-Wno-unused-function;-Wno-missing-declarations")

    # Switch 22.0+ may store compressed NSO segments as ZBIC, a Nintendo
    # zstd variant. The pinned Eden source predates upstream #4482.
    set(ZBIC_DIR "${PORT_ROOT}/.deps/zbic-11b08f27/src")
    if(NOT EXISTS "${ZBIC_DIR}/zstd.c")
        message(FATAL_ERROR "ZBIC source is missing (${ZBIC_DIR}); run make deps")
    endif()
    target_sources(common PRIVATE "${EDEN_PORT_DIR}/zbic_compression.cpp")
    target_include_directories(common PRIVATE "${ZBIC_DIR}")
    set_source_files_properties("${EDEN_PORT_DIR}/zbic_compression.cpp" PROPERTIES
        COMPILE_OPTIONS "-Wno-unused-function;-Wno-missing-declarations;-Wno-shadow")
    target_include_directories(core PRIVATE "${EDEN_PORT_DIR}")
    target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")
endif()
# Use the already-qualified no-arena allocation contract in the full core.
get_target_property(common_sources common SOURCES)
list(REMOVE_ITEM common_sources host_memory.cpp sparse_large_vector.cpp)
set_property(TARGET common PROPERTY SOURCES "${common_sources}")
target_sources(common PRIVATE "${PORT_ROOT}/src/host_memory.cpp" "${PORT_ROOT}/src/memory_pages.cpp")

# Complete native sparse vector header is owned by Encore, not constructed
# at configure time. Preserve the prior include-overlay selection order.
set(EDEN_MAINTAINED_SPARSE_VECTOR
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/sparse_large_vector.h")
if(NOT EXISTS "${EDEN_MAINTAINED_SPARSE_VECTOR}")
    message(FATAL_ERROR "Missing maintained sparse vector header")
endif()
file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/sparse/common")
configure_file("${EDEN_MAINTAINED_SPARSE_VECTOR}"
    "${PORT_BUILD_DIR}/sparse/common/sparse_large_vector.h" COPYONLY)

# The fiber transition fix is a complete, versioned C++ translation unit.
# It was previously regenerated by CMake string(REPLACE) at each configure.
# The pinned original stays immutable in vendor/sources for audit/provenance.
set(EDEN_FIBER_ACTIVE "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/fiber.cpp")
if(NOT EXISTS "${EDEN_FIBER_ACTIVE}")
    message(FATAL_ERROR "Missing tracked Encore fiber source")
endif()
get_target_property(common_sources common SOURCES)
list(REMOVE_ITEM common_sources fiber.cpp)
list(APPEND common_sources "${EDEN_FIBER_ACTIVE}")
set_property(TARGET common PROPERTY SOURCES "${common_sources}")

get_target_property(jit_sources dynarmic SOURCES)
list(FILTER jit_sources EXCLUDE REGEX "exception_handler_posix\\.cpp$")
set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
# A32 fastmem: src/host_memory.cpp aliases 32-bit guest memory into a 4 GiB window at
# the PS5's 16 KiB page size; this handler sends faulting JIT accesses to their
# page-table fallback. Without it the generic handler keeps fastmem off.
option(EDEN_A32_FASTMEM "A32 fastmem window with JIT fault recovery" ON)
if(EDEN_A32_FASTMEM AND (PS5_NATIVE OR CMAKE_SYSTEM_NAME STREQUAL "Linux"))
    target_sources(dynarmic PRIVATE "${EDEN_PORT_DIR}/fastmem_handler.cpp")
else()
    target_sources(dynarmic PRIVATE "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/exception_handler_generic.cpp")
endif()

  # Page-local W^X: constants stay RW/NX; old code stays RX unless patched.
  # Apply the same derivative to Linux host correctness/pressure tests.
if(PS5_NATIVE OR CMAKE_SYSTEM_NAME STREQUAL "Linux")
set(code_relative "dynarmic/backend/x64/block_of_code")
file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/${code_relative}.h" code_header)
string(REPLACE "    bool prelude_complete = false;"
      "    size_t protection_end = 0;\n    size_t executable_end = 0;\n    size_t write_begin = 0;\n    bool writing = true;\n    std::vector<size_t> patch_pages;\n    bool prelude_complete = false;" code_header "${code_header}")
  write_derived("${PORT_BUILD_DIR}/include/${code_relative}.h" "#include <vector>\n${code_header}")
target_include_directories(dynarmic BEFORE PUBLIC "${PORT_BUILD_DIR}/include")
file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/${code_relative}.cpp" code_source)
include("${EDEN_PORT_DIR}/jit-alias.cmake")
    string(REPLACE "#include \"dynarmic/backend/x64/block_of_code.h\""
        "#include \"dynarmic/backend/x64/block_of_code.h\"\n#include \"${EDEN_PORT_DIR}/jit-allocator.h\"\n#include \"${EDEN_PORT_DIR}/jit-sparse-commit.h\"" code_source "${code_source}")
    string(REPLACE "        , nullptr)\n    , constant_pool"
        "        , EdenJitAllocator())\n    , constant_pool" code_source "${code_source}")
if(PS5_NATIVE)
    string(PREPEND code_source "#define EDEN_JIT_ALIAS_NATIVE 1\n")
    string(REPLACE "    GenRunCode(rcp);"
        "    std::printf(\"EDEN_JIT_FEATURES mask=%x cache_bytes=%zu\\n\", unsigned(GetHostFeatures()), total_code_size);\n    GenRunCode(rcp);" code_source "${code_source}")
    # Unix Dynarmic assumes memory is eagerly backed. The PS5 sparse path
    # commits each new executable chunk at its existing virtual address.
    # A selected sparse allocator NEVER falls back to dense RX; the commit
    # implementation already checks region ownership/capacity under its lock.
    # Skip the earlier redundant IsSparseJitCode() map lookup and mutex lock
    # for each compiled guest block (4 guest workers compete otherwise).
    set(jit_commit_anchor "void BlockOfCode::EnsureMemoryCommitted([[maybe_unused]] size_t codesize) {\n")
    string(FIND "${code_source}" "${jit_commit_anchor}" jit_commit_at)
    if(jit_commit_at LESS 0)
        message(FATAL_ERROR "Pinned Dynarmic JIT commit boundary changed")
    endif()
    string(REPLACE "${jit_commit_anchor}"
        "${jit_commit_anchor}#ifdef PS5_NATIVE\n    if (::Eden::Experimental::sparse_jit_cache.load(std::memory_order_relaxed)) {\n        const size_t written = getSize();\n        const auto target = ::Eden::Jit::PlanSparseCommit(written, codesize, maxSize_);\n        if (!target.valid ||\n            !::Common::CommitSparseJitCode(const_cast<u8*>(getCode()), target.bytes)) {\n            std::fprintf(stderr, \"EDEN_JIT_SPARSE_COMMIT_FAILED used=%zu next=%zu capacity=%zu\\n\", written, codesize, maxSize_);\n            throw std::bad_alloc{};\n        }\n        if (target.clamped)\n            std::fprintf(stderr, \"EDEN_JIT_SPARSE_PRECOMMIT_CLAMPED used=%zu hint=%zu target=%zu capacity=%zu\\n\",\n                         written, codesize, target.bytes, maxSize_);\n        return;\n    }\n#endif\n"
        code_source "${code_source}")
endif()
  # ConstantPool has completed construction before this body. Isolate its last
  # page from executable prelude, without accessing fields during construction.
  string(REPLACE "    EnableWriting();\n    EnsureMemoryCommitted(PRELUDE_COMMIT_SIZE);"
      "    align(sysconf(_SC_PAGESIZE));\n    write_begin = getSize();\n    executable_end = write_begin;\n    if (hasWritableAlias() && mprotect(const_cast<u8*>(getCode()), write_begin, PROT_READ) != 0) std::abort();\n    EnableWriting();\n    EnsureMemoryCommitted(PRELUDE_COMMIT_SIZE);" code_source "${code_source}")
  # Keep generated helper routines RX even while guest blocks are being patched.
  string(REPLACE "    prelude_complete = true;"
      "    align(sysconf(_SC_PAGESIZE));\n    prelude_complete = true;" code_source "${code_source}")
  file(READ "${EDEN_PORT_DIR}/jit-permissions.inc" permission_methods)
  string(FIND "${code_source}" "void BlockOfCode::EnableWriting()" permission_start)
  string(FIND "${code_source}" "size_t BlockOfCode::SpaceRemaining()" permission_end)
  if(permission_start LESS 0 OR permission_end LESS permission_start)
      message(FATAL_ERROR "Pinned JIT permission methods changed")
  endif()
  string(SUBSTRING "${code_source}" 0 ${permission_start} code_prefix)
  string(SUBSTRING "${code_source}" ${permission_end} -1 code_suffix)
  set(code_source "${code_prefix}${permission_methods}\n${code_suffix}")
  string(REPLACE "    setSize(required_size);" [=[    ASSERT(writing);
    ASSERT(!prelude_complete || required_size >= size_t(reinterpret_cast<const u8*>(code_begin) - getCode()));
    protection_end = std::max(protection_end, getSize());
    // Backward cursor moves are EmitX64::Patch sites, at most 23 bytes.
    static const size_t page = sysconf(_SC_PAGESIZE);
    const size_t patch_end = std::min(write_begin, required_size + 23);
    size_t first_new = patch_end, last_new = patch_end;
    for (size_t offset = required_size & ~(page - 1); !hasWritableAlias() && offset < patch_end; offset += page) {
        if (std::find(patch_pages.begin(), patch_pages.end(), offset) == patch_pages.end()) {
            patch_pages.push_back(offset);
            first_new = std::min(first_new, offset);
            last_new = offset + page;
        }
    }
    if (last_new > first_new) ProtectMemory(getCode() + first_new, last_new - first_new, false);
    setSize(required_size);
    protection_end = std::max(protection_end, getSize());]=] code_source "${code_source}")
  string(REPLACE "    size_t current_size = getCurr<const u8*>()"
      "    ASSERT(size <= 23);\n    size_t current_size = getCurr<const u8*>()" code_source "${code_source}")
string(REPLACE "    mprotect(reinterpret_cast<void*>(roundAddr), size + (iaddr - roundAddr), mode);"
    "    const size_t span = (size + (iaddr - roundAddr) + pageSize - 1) & ~(pageSize - 1);\n    if (mprotect(reinterpret_cast<void*>(roundAddr), span, mode) != 0) std::abort();" code_source "${code_source}")
  write_derived("${PORT_BUILD_DIR}/block_of_code.cpp" "#include <algorithm>\n#include <cstdio>\n#include <cstdlib>\n#include <new>\n#include <unistd.h>\n${code_source}")
get_target_property(jit_sources dynarmic SOURCES)
list(FILTER jit_sources EXCLUDE REGEX "(^|/)block_of_code\\.cpp$")
set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
target_sources(dynarmic PRIVATE "${PORT_BUILD_DIR}/block_of_code.cpp")
# The native PS5 code-commit branch is inside this generated Dynarmic unit.
# PS5_NATIVE is not inherited from eden-headless/common by this target.
# Scope the definition to the one source that owns the kernel mapping hook.
if(PS5_NATIVE)
    set_property(SOURCE "${PORT_BUILD_DIR}/block_of_code.cpp"
        TARGET_DIRECTORY dynarmic APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1")
endif()
foreach(bits 32 64)
    file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/a${bits}_emit_x64.cpp" emitter)
    if(bits EQUAL 64)
        file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/a64_emit_x64.h" emitter_header)
        if(EDEN_SHARED_JIT OR EDEN_JIT_COMPILE_BATCH)
            string(REPLACE "Emit(IR::Block& block) noexcept" "Emit(IR::Block& block, bool publish = true) noexcept" emitter_header "${emitter_header}")
            string(REPLACE "A64EmitX64::Emit(IR::Block& block) noexcept" "A64EmitX64::Emit(IR::Block& block, bool publish) noexcept" emitter "${emitter}")
            string(REPLACE "    code.DisableWriting();\n    shared_labels.clear();" "    if (publish) code.DisableWriting();\n    shared_labels.clear();" emitter "${emitter}")
        endif()
        if(EDEN_SHARED_JIT)
            eden_shared_jit_emitter_header()
        endif()
        write_derived("${PORT_BUILD_DIR}/include/dynarmic/backend/x64/a64_emit_x64.h" "${emitter_header}")
    endif()
    set(lookup_transitions "        code.DisableWriting();\n        (*fast_dispatch_table_lookup)(location.Value()) = {};\n        code.EnableWriting();")
    string(FIND "${emitter}" "${lookup_transitions}" lookup_offset)
    if(lookup_offset LESS 0)
        message(FATAL_ERROR "Pinned JIT fast-dispatch invalidation changed")
    endif()
    string(REPLACE "${lookup_transitions}"
        "        // Prelude occupies separate RX pages throughout guest-code patching.\n        (*fast_dispatch_table_lookup)(location.Value()) = {};" emitter "${emitter}")
    if(bits EQUAL 64 AND EDEN_SHARED_JIT)
        eden_shared_jit_emitter()
    endif()
    write_derived("${PORT_BUILD_DIR}/a${bits}_emit_x64.cpp" "${emitter}")
    get_target_property(jit_sources dynarmic SOURCES)
    list(FILTER jit_sources EXCLUDE REGEX "(^|/)a${bits}_emit_x64\\.cpp$")
    set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
    target_sources(dynarmic PRIVATE "${PORT_BUILD_DIR}/a${bits}_emit_x64.cpp")
endforeach()
endif()

# Compiled guest block ranges by 4 KiB page. Both the header and its
# translation unit have exactly one maintained owner in encore-active.
# This remains selected regardless of EDEN_SHARED_JIT.
set(EDEN_MAINTAINED_BLOCK_RANGE_DIR
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/backend")
foreach(EDEN_BLOCK_RANGE_FILE IN ITEMS block_range_information.cpp block_range_information.h)
    if(NOT EXISTS "${EDEN_MAINTAINED_BLOCK_RANGE_DIR}/${EDEN_BLOCK_RANGE_FILE}")
        message(FATAL_ERROR "Missing maintained Dynarmic block-range ${EDEN_BLOCK_RANGE_FILE}")
    endif()
endforeach()
configure_file(
    "${EDEN_MAINTAINED_BLOCK_RANGE_DIR}/block_range_information.h"
    "${PORT_BUILD_DIR}/include/dynarmic/backend/block_range_information.h" COPYONLY)
get_target_property(range_sources dynarmic SOURCES)
list(FILTER range_sources EXCLUDE REGEX "(^|/)block_range_information\\.cpp$")
set_property(TARGET dynarmic PROPERTY SOURCES "${range_sources}")
target_sources(dynarmic PRIVATE
    "${EDEN_MAINTAINED_BLOCK_RANGE_DIR}/block_range_information.cpp")
# Keep the native header's original include shadowing and target-wide layout ABI.
target_compile_definitions(dynarmic PRIVATE EDEN_BLOCK_RANGE_PAGES=1)
if(EDEN_SHARED_JIT)
    eden_shared_jit_sources()
endif()
if(PS5_NATIVE OR CMAKE_SYSTEM_NAME STREQUAL "Linux")
    eden_reg_alloc_sources()
endif()

# Patch lookup must not create a large empty record for every compiled block.
# Keep the upstream implementation and change only its absent-target path.
file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/emit_x64.cpp" emitter)
set(patch_lookup "    const PatchInformation& patch_info = patch_information[target_desc];")
string(FIND "${emitter}" "${patch_lookup}" patch_lookup_offset)
if(patch_lookup_offset LESS 0)
    message(FATAL_ERROR "Pinned JIT patch lookup changed")
endif()
string(REPLACE "${patch_lookup}"
    "    const auto patch = patch_information.find(target_desc);\n    if (patch == patch_information.end()) return;\n    const PatchInformation& patch_info = patch->second;" emitter "${emitter}")
if(PS5_NATIVE)
    # PS5 has no perf-map writer. Its no-op still evaluates the formatted name.
    string(REPLACE "    PerfMapRegister(entrypoint, code.getCurr(), LocationDescriptorToFriendlyName(descriptor));"
        "" emitter "${emitter}")
endif()
write_derived("${PORT_BUILD_DIR}/emit_x64.cpp" "${emitter}")
get_target_property(jit_sources dynarmic SOURCES)
list(FILTER jit_sources EXCLUDE REGEX "(^|/)emit_x64\\.cpp$")
set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
target_sources(dynarmic PRIVATE "${PORT_BUILD_DIR}/emit_x64.cpp")

# Dynarmic scalar translation and optimizer are tracked complete sources.
# impl/impl.cpp is included once by its adjacent translator.
set(EDEN_MAINTAINED_SCALAR_IMPL
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/frontend/A64/translate/impl/impl.cpp")
set(EDEN_MAINTAINED_SCALAR_TRANSLATOR
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/frontend/A64/translate/a64_translate.cpp")
set(EDEN_MAINTAINED_SCALAR_OPT
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/ir/opt_passes.cpp")
foreach(EDEN_MAINTAINED_SCALAR_SOURCE IN ITEMS
        "${EDEN_MAINTAINED_SCALAR_IMPL}"
        "${EDEN_MAINTAINED_SCALAR_TRANSLATOR}"
        "${EDEN_MAINTAINED_SCALAR_OPT}")
    if(NOT EXISTS "${EDEN_MAINTAINED_SCALAR_SOURCE}")
        message(FATAL_ERROR "Missing maintained Dynarmic scalar file ${EDEN_MAINTAINED_SCALAR_SOURCE}")
    endif()
endforeach()
get_target_property(jit_sources dynarmic SOURCES)
list(FILTER jit_sources EXCLUDE REGEX "(^|/)a64_translate\\.cpp$")
list(FILTER jit_sources EXCLUDE REGEX "(^|/)opt_passes\\.cpp$")
set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
target_sources(dynarmic PRIVATE
    "${EDEN_MAINTAINED_SCALAR_TRANSLATOR}"
    "${EDEN_MAINTAINED_SCALAR_OPT}")

# Keep the checked page-table path, but use x86 scaled addressing and avoid a
# 64-bit mask load for Eden's packed pointer. Apply to both A32 and A64 emitters.
set(memory_relative "dynarmic/backend/x64/emit_x64_memory.h")
file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/${memory_relative}" memory_emitter)
foreach(index IN ITEMS "tmp.cvt64()" "tmp")
    set(lookup "    code.shl(tmp, int(ctx.conf.page_table_log2_stride));\n    code.mov(page, qword[r14 + ${index}]);")
    string(FIND "${memory_emitter}" "${lookup}" offset)
    if(offset LESS 0)
        message(FATAL_ERROR "Pinned page-table indexing changed")
    endif()
    string(REPLACE "${lookup}" [=[    if (ctx.conf.page_table_log2_stride <= 3) {
        code.mov(page, qword[r14 + tmp * (1 << ctx.conf.page_table_log2_stride)]);
    } else {
        code.shl(tmp, int(ctx.conf.page_table_log2_stride));
        code.mov(page, qword[r14 + tmp]);
    }]=] memory_emitter "${memory_emitter}")
endforeach()
set(pointer_mask "    // mask away attributes\n    if (ctx.conf.page_table_pointer_mask == 0) {")
set(pointer_end "        code.sar(page, *ctx.conf.page_table_sign_extension);\n    }\n\n    code.jz")
foreach(anchor IN ITEMS pointer_mask pointer_end)
    string(FIND "${memory_emitter}" "${${anchor}}" offset)
    if(offset LESS 0)
        message(FATAL_ERROR "Pinned page-table pointer decoding changed")
    endif()
endforeach()
string(REPLACE "${pointer_mask}" [=[    // Eden packs pointer bits 12..55. Sign extension removes the upper
    // attributes first, leaving a page mask that fits an x86 immediate.
    if (ctx.conf.page_table_pointer_mask == 0x00fffffffffff000ULL &&
        ctx.conf.page_table_sign_extension == 8) {
        code.shl(page, 8);
        code.sar(page, 8);
        code.and_(page, -4096);
    } else {
    // mask away attributes
    if (ctx.conf.page_table_pointer_mask == 0) {]=] memory_emitter "${memory_emitter}")
string(REPLACE "${pointer_end}" "        code.sar(page, *ctx.conf.page_table_sign_extension);\n    }\n    }\n\n    code.jz"
    memory_emitter "${memory_emitter}")
# The packed-pointer decoder above uses only immediates. Like upstream's
# unmasked absolute-offset path, it can reuse the index register for the page.
# Relative offsets and other pointer formats still need two scratch registers.
set(reuse_index "ctx.conf.absolute_offset_page_table && ctx.conf.page_table_pointer_mask == 0 ? page")
string(FIND "${memory_emitter}" "${reuse_index}" reuse_offset)
if(reuse_offset LESS 0)
    message(FATAL_ERROR "Pinned page-table scratch allocation changed")
endif()
string(REPLACE "${reuse_index}"
    "ctx.conf.absolute_offset_page_table && (ctx.conf.page_table_pointer_mask == 0 || (ctx.conf.page_table_pointer_mask == 0x00fffffffffff000ULL && ctx.conf.page_table_sign_extension == 8)) ? page"
    memory_emitter "${memory_emitter}")
# Eden's mark is bit zero: use a normal test/branch instead of extracting carry.
# Keep the upstream bit-test path for every other configured mark position.
set(mark_test "        code.bt(page, *ctx.conf.page_table_marked_bit);\n        code.jc(abort, code.T_NEAR);")
string(FIND "${memory_emitter}" "${mark_test}" mark_offset)
if(mark_offset LESS 0)
    message(FATAL_ERROR "Pinned page-table mark check changed")
endif()
string(REPLACE "${mark_test}" [=[        if (*ctx.conf.page_table_marked_bit == 0) {
            code.test(page.cvt32(), 1);
            code.jnz(abort, code.T_NEAR);
        } else {
            code.bt(page, *ctx.conf.page_table_marked_bit);
            code.jc(abort, code.T_NEAR);
        }]=] memory_emitter "${memory_emitter}")
# Retain the ordinary page-table lookup on window misses. Reserve scratch
    # registers before branching: allocator spills must run on both paths.
    set(lookup_args "Xbyak::Label& abort, Xbyak::Reg64 vaddr)")
    string(REPLACE "${lookup_args};"
        "Xbyak::Label& abort, Xbyak::Reg64 vaddr, std::optional<std::pair<Xbyak::Reg64, Xbyak::Reg64>> scratch = std::nullopt);"
        memory_emitter "${memory_emitter}")
    string(REPLACE "${lookup_args} {"
        "Xbyak::Label& abort, Xbyak::Reg64 vaddr, std::optional<std::pair<Xbyak::Reg64, Xbyak::Reg64>> scratch) {"
        memory_emitter "${memory_emitter}")
    string(REPLACE "const Xbyak::Reg64 page = ctx.reg_alloc.ScratchGpr(code);"
        "const Xbyak::Reg64 page = scratch ? scratch->first : ctx.reg_alloc.ScratchGpr(code);"
        memory_emitter "${memory_emitter}")
    string(REPLACE "const Xbyak::Reg64 tmp = ctx.conf.absolute_offset_page_table"
        "const Xbyak::Reg64 tmp = scratch ? scratch->second : ctx.conf.absolute_offset_page_table"
        memory_emitter "${memory_emitter}")
    set(memory_inc "dynarmic/backend/x64/emit_x64_memory.cpp.inc")
    file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/${memory_inc}" memory_source)
    # Exclusive operations already allocated these two registers before their
    # monitor/early-exit branches. Never introduce a conditional allocator spill.
    string(FIND "${memory_source}" "void AxxEmitX64::EmitExclusiveReadMemoryInline" exclusive_start)
    string(SUBSTRING "${memory_source}" 0 ${exclusive_start} memory_prefix)
    string(SUBSTRING "${memory_source}" ${exclusive_start} -1 memory_exclusive)
    # Keep upstream's monitor and compare/exchange implementation, but allow
    # checked page-table addresses when direct fastmem is unavailable.
    string(REPLACE "ASSERT(conf.global_monitor && conf.fastmem_pointer);"
        "ASSERT(conf.global_monitor && (conf.fastmem_pointer || conf.page_table));"
        memory_exclusive "${memory_exclusive}")
    string(REPLACE "if (!exception_handler.SupportsFastmem())"
        "if (!conf.page_table && !exception_handler.SupportsFastmem())"
        memory_exclusive "${memory_exclusive}")
    string(REPLACE "if (fastmem_marker) {" "if (fastmem_marker || conf.page_table) {"
        memory_exclusive "${memory_exclusive}")
    string(REPLACE "bool require_abort_handling = false;" "bool require_abort_handling = !fastmem_marker;"
        memory_exclusive "${memory_exclusive}")
    foreach(arguments IN ITEMS "" ", tmp")
        set(old "= EmitFastmemVAddr(code, ctx, *abort, vaddr, require_abort_handling${arguments});")
        string(FIND "${memory_exclusive}" "${old}" site)
        if(site LESS 0)
            message(FATAL_ERROR "Pinned exclusive lookup changed")
        endif()
        string(REPLACE "${old}"
            "= fastmem_marker ? EmitFastmemVAddr(code, ctx, *abort, vaddr, require_abort_handling${arguments}) : EmitExclusiveVAddrLookup(code, ctx, bitsize, *abort, vaddr, tmp2, tmp);"
            memory_exclusive "${memory_exclusive}")
    endforeach()
    string(REPLACE "fastmem_patch_info.emplace(" "if (fastmem_marker) fastmem_patch_info.emplace("
        memory_exclusive "${memory_exclusive}")
    set(memory_source "${memory_prefix}${memory_exclusive}")
    include("${EDEN_PORT_DIR}/scalar-memory.cmake")
    if(EDEN_A32_FASTMEM)
        include("${EDEN_PORT_DIR}/checked-fastmem.cmake")
    endif()
    if(EDEN_SHARED_JIT)
        eden_shared_jit_memory_inc()
    endif()
    write_derived("${PORT_BUILD_DIR}/include/${memory_inc}" "${memory_source}")
set(exclusive_lookup [=[template<typename EmitContext>
Xbyak::RegExp EmitExclusiveVAddrLookup(BlockOfCode& code, EmitContext& ctx, size_t bitsize,
        Xbyak::Label& abort, Xbyak::Reg64 vaddr, Xbyak::Reg64 page, Xbyak::Reg64 tmp) {
    if (bitsize > 8) {
        code.test(vaddr, u32(bitsize / 8 - 1));
        code.jnz(abort, code.T_NEAR);
    }
    // Natural alignment excludes page crossings, including CMPXCHG16B's
    // stricter alignment requirement. Skip the duplicate generic check.
    return EmitVAddrLookup(code, ctx, 8, abort, vaddr, std::make_optional(std::pair{page, tmp}));
}

]=])
set(fastmem_declaration "template<typename EmitContext>\nXbyak::RegExp EmitFastmemVAddr")
string(REPLACE "${fastmem_declaration}" "${exclusive_lookup}${fastmem_declaration}"
    memory_emitter "${memory_emitter}")
if(EDEN_SHARED_JIT)
    eden_shared_jit_memory_header()
endif()
write_derived("${PORT_BUILD_DIR}/include/${memory_relative}" "${memory_emitter}")
# New include overlays do not invalidate objects whose depfile still names
# upstream headers. Derive both translation units so the first build cannot
# silently keep old objects; subsequent depfiles track the overlay normally.
get_target_property(jit_sources dynarmic SOURCES)
foreach(bits 32 64)
    set(memory_unit "a${bits}_emit_x64_memory.cpp")
    file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/${memory_unit}" memory_source)
    if(EDEN_SHARED_JIT)
        eden_shared_jit_memory_unit(${bits})
    endif()
    write_derived("${PORT_BUILD_DIR}/${memory_unit}" "${memory_source}")
    list(FILTER jit_sources EXCLUDE REGEX "(^|/)a${bits}_emit_x64_memory\\.cpp$")
    list(APPEND jit_sources "${PORT_BUILD_DIR}/${memory_unit}")
endforeach()
set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")


if(PS5_NATIVE)
    # The native spin-lock adjustment is a complete Encore source.
    set(EDEN_MAINTAINED_SPIN_LOCK
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/common/spin_lock_x64.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_SPIN_LOCK}")
        message(FATAL_ERROR "Missing maintained native Dynarmic spin lock")
    endif()
    get_target_property(jit_sources dynarmic SOURCES)
    list(FILTER jit_sources EXCLUDE REGEX "(^|/)spin_lock_x64\\.cpp$")
    set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
    target_sources(dynarmic PRIVATE "${EDEN_MAINTAINED_SPIN_LOCK}")
endif()

# Diagnostics record actual automatic cache evacuation, not explicit clears.
    set(jit_interface "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/a64_interface.cpp")
    file(READ "${jit_interface}" jit_source)
    if(EDEN_JIT_COMPILE_BATCH AND (PS5_NATIVE OR CMAKE_SYSTEM_NAME STREQUAL "Linux"))
        set(compile_begin "        const auto get_code = [this](u64 vaddr) { return conf.callbacks->MemoryReadCode(vaddr); };")
        set(compile_end "        return emitter.Emit(ir_block).entrypoint;")
        string(FIND "${jit_source}" "${compile_begin}" begin)
        string(FIND "${jit_source}" "${compile_end}" end)
        if(begin LESS 0 OR end LESS begin)
            message(FATAL_ERROR "Pinned JIT compilation boundary changed")
        endif()
        string(LENGTH "${compile_end}" end_length)
        math(EXPR end "${end} + ${end_length}")
        string(SUBSTRING "${jit_source}" 0 ${begin} prefix)
        string(SUBSTRING "${jit_source}" ${end} -1 suffix)
        file(READ "${EDEN_PORT_DIR}/jit-compile-batch.inc" compile_batch)
        set(jit_source "${prefix}${compile_batch}${suffix}")
    endif()
    set(pressure_site "            // Immediately evacuate cache")
    string(FIND "${jit_source}" "${pressure_site}" pressure_offset)
    if(pressure_offset LESS 0)
        message(FATAL_ERROR "Pinned JIT cache evacuation changed.")
    endif()
    set(pressure_log "            std::fprintf(stderr, \"EDEN_JIT_PRESSURE core=%u capacity=%u remaining=%zu\\n\", unsigned(conf.processor_id), unsigned(conf.code_cache_size), block_of_code.SpaceRemaining());")
    if(PS5_NATIVE)
        # Every whole-cache evacuation (first 200 per core, with the monotonic time the
        # performance reports use) and a counter for them (eden_jit_evacuation).
        set(pressure_log "            static thread_local unsigned pressure_count;\n            if (eden_native_detailed_logging && eden_native_detailed_logging() && ++pressure_count <= 200) std::printf(\"EDEN_JIT_PRESSURE core=%u capacity=%u remaining=%zu count=%u mono_ns=%lld\\n\", unsigned(conf.processor_id), unsigned(conf.code_cache_size), block_of_code.SpaceRemaining(), pressure_count, static_cast<long long>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count()));\n            if (eden_jit_evacuation) eden_jit_evacuation(unsigned(conf.processor_id));")
    endif()
    string(REPLACE "${pressure_site}"
        "${pressure_log}\n${pressure_site}"
        jit_source "${jit_source}")
    if(PS5_NATIVE AND EDEN_DEV_PROFILE)
        # Development: time every block compilation (cache misses) per guest core.
        set(compile_site "        if (auto block = emitter.GetBasicBlock(descriptor))\n            return block->entrypoint;\n")
        string(FIND "${jit_source}" "${compile_site}" compile_site_at)
        if(compile_site_at LESS 0)
            message(FATAL_ERROR "Pinned JIT block lookup changed.")
        endif()
        # R298: zero per-block clock reads with Detailed Logging OFF.
        # Keep per-core compilation timings with logging ON, where the
        # diagnostic collection is explicitly requested by the user.
        set(quiet_jit_timer [=[
        struct EdenCompileTimer {
            unsigned core;
            bool active;
            std::chrono::steady_clock::time_point start{};
            explicit EdenCompileTimer(unsigned c) : core(c),
                active(eden_native_detailed_logging && eden_native_detailed_logging()) {
                if (active) start = std::chrono::steady_clock::now();
            }
            ~EdenCompileTimer() {
                if (active && eden_jit_compile)
                    eden_jit_compile(core, static_cast<unsigned long long>(
                        std::chrono::duration_cast<std::chrono::nanoseconds>(
                            std::chrono::steady_clock::now() - start).count()));
            }
        } eden_compile_timer{unsigned(conf.processor_id)};
]=])
        string(REPLACE "${compile_site}" "${compile_site}${quiet_jit_timer}" jit_source "${jit_source}")
        if(EDEN_JIT_COMPILE_BATCH)
            # Development: the compile phases of every block (eden_jit_phases).
            set(phase_old "            A64::Translate(ir_block, arch_descriptor, get_code, {conf.define_unpredictable_behaviour, conf.wall_clock_cntpct});\n            Optimization::Optimize(ir_block, conf, polyfill_options);\n            const auto entrypoint = emitter.Emit(ir_block, false).entrypoint;")
            string(FIND "${jit_source}" "${phase_old}" phase_at)
            if(phase_at LESS 0)
                message(FATAL_ERROR "Pinned JIT compile batch changed.")
            endif()
            string(REPLACE "${phase_old}" "            const auto eden_t0 = std::chrono::steady_clock::now();\n            A64::Translate(ir_block, arch_descriptor, get_code, {conf.define_unpredictable_behaviour, conf.wall_clock_cntpct});\n            const auto eden_t1 = std::chrono::steady_clock::now();\n            Optimization::Optimize(ir_block, conf, polyfill_options);\n            const auto eden_t2 = std::chrono::steady_clock::now();\n            const auto entrypoint = emitter.Emit(ir_block, false).entrypoint;\n            if (eden_jit_phases) {\n                const auto eden_ns = [](auto a, auto b) { return static_cast<unsigned long long>(std::chrono::duration_cast<std::chrono::nanoseconds>(b - a).count()); };\n                eden_jit_phases(unsigned(conf.processor_id), eden_ns(eden_t0, eden_t1), eden_ns(eden_t1, eden_t2), eden_ns(eden_t2, std::chrono::steady_clock::now()), descriptor.Value());\n            }" jit_source "${jit_source}")
            string(PREPEND jit_source "extern \"C\" void eden_jit_phases(unsigned core, unsigned long long translate, unsigned long long optimize, unsigned long long emit, unsigned long long location) __attribute__((weak));\n")
        endif()
    endif()
    if(PS5_NATIVE)
        # If a demand-committed code arena cannot get another physical
        # 2 MiB chunk, use Dynarmic's existing whole-cache invalidation
        # protocol to reuse pages already committed. Retrying once avoids
        # an unconditional process abort on recoverable JIT memory pressure.
        set(jit_retry_site "        block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);")
        string(FIND "${jit_source}" "${jit_retry_site}" jit_retry_at)
        if(jit_retry_at LESS 0)
            message(FATAL_ERROR "Pinned A64 JIT commit checkpoint changed")
        endif()
        set(jit_retry_replacement
            "        try {\n            block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);\n        } catch (const std::bad_alloc&) {\n            invalidate_entire_cache = true;\n            PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);\n            block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);\n        }")
        string(REPLACE "${jit_retry_site}" "${jit_retry_replacement}" jit_source "${jit_source}")
    endif()
    if(EDEN_SHARED_JIT)
        eden_shared_jit_interface()
    endif()
    write_derived("${PORT_BUILD_DIR}/a64_interface.cpp" "#include <chrono>\n#include <cstdio>\n#include <new>\nextern \"C\" bool eden_native_detailed_logging() noexcept __attribute__((weak));\nextern \"C\" void eden_jit_evacuation(unsigned core) __attribute__((weak));\nextern \"C\" void eden_jit_compile(unsigned core, unsigned long long ns) __attribute__((weak));\n${jit_source}")
    get_target_property(jit_sources dynarmic SOURCES)
    list(FILTER jit_sources EXCLUDE REGEX "(^|/)a64_interface\\.cpp$")
    set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
    target_sources(dynarmic PRIVATE "${PORT_BUILD_DIR}/a64_interface.cpp")

if(PS5_NATIVE)
    file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/a32_interface.cpp" a32_interface)
    string(REPLACE "            invalidate_entire_cache = true;"
        "            static thread_local unsigned pressure_count;\n            if (++pressure_count <= 3) std::printf(\"EDEN_JIT_PRESSURE bits=32 core=%u capacity=%u remaining=%zu\\n\", unsigned(conf.processor_id), unsigned(conf.code_cache_size), block_of_code.SpaceRemaining());\n            invalidate_entire_cache = true;"
        a32_interface "${a32_interface}")
    # Mirror the same retry for A32 guest code; avoid a title whitelist.
    set(jit_retry_site "        block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);")
    string(FIND "${a32_interface}" "${jit_retry_site}" a32_retry_at)
    if(a32_retry_at LESS 0)
        message(FATAL_ERROR "Pinned A32 JIT commit checkpoint changed")
    endif()
    set(jit_retry_replacement
        "        try {\n            block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);\n        } catch (const std::bad_alloc&) {\n            invalidate_entire_cache = true;\n            PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);\n            block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);\n        }")
    string(REPLACE "${jit_retry_site}" "${jit_retry_replacement}" a32_interface "${a32_interface}")
    set(a32_emit "        return emitter.Emit(ir_block);\n    }")
    string(FIND "${a32_interface}" "${a32_emit}" a32_emit_at)
    if(a32_emit_at LESS 0)
        message(FATAL_ERROR "Pinned A32 block emission changed")
    endif()
    string(REPLACE "${a32_emit}"
        "        const auto emitted = emitter.Emit(ir_block);\n        if (eden_jit_block)\n            eden_jit_block(unsigned(conf.processor_id), descriptor.Value(), reinterpret_cast<const void*>(emitted.entrypoint), emitted.size);\n        return emitted;\n    }"
        a32_interface "${a32_interface}")
    write_derived("${PORT_BUILD_DIR}/a32_interface.cpp" "#include <cstdio>\n#include <new>\nextern \"C\" void eden_jit_block(unsigned core, unsigned long long location, const void* entry, unsigned long long size) __attribute__((weak));\n${a32_interface}")
    get_target_property(jit_sources dynarmic SOURCES)
    list(FILTER jit_sources EXCLUDE REGEX "(^|/)a32_interface\\.cpp$")
    set_property(TARGET dynarmic PROPERTY SOURCES "${jit_sources}")
    target_sources(dynarmic PRIVATE "${PORT_BUILD_DIR}/a32_interface.cpp")
endif()

# Dynarmic keeps its Xbyak dependency PRIVATE; the PS5-specific core
# wrapper also needs Xbyak::Error for typed allocator-only startup retries.
# Expose the imported header-only target to core without changing Dynarmic's
# public dependency surface or pulling a new Xbyak version.
if(PS5_NATIVE)
    target_link_libraries(core PRIVATE xbyak::xbyak)
endif()
# Carry both qualified JIT configuration changes into the real core wrappers.
# Generate local derivatives; the pinned dependency itself remains unchanged.
get_target_property(core_sources core SOURCES)
foreach(bits 32 64)
    set(relative "arm/dynarmic/arm_dynarmic_${bits}.cpp")
    file(READ "${PROJECT_SOURCE_DIR}/src/core/${relative}" wrapper)
    string(REPLACE "Common::PageTable::SIGN_BIT" "std::countl_zero(Common::PageTable::ATTRIBUTE_MASK)" wrapper "${wrapper}")
    # Without fastmem every LDREX/STREX left JIT code through a callback under the
    # global monitor lock (~7,000 pairs/frame in a measured racing game). The exclusive
    # emitter patch below supports page-table addresses; eden-memory-check covers
    # it for A64 and A32 (atomic loops, 1-4 cores).
    # Stability-first release default. The forced page-table exclusive path is faster, but a
    # hardware-only soft hang can leave the guest stopped while presentation/input remain alive.
    # Keep the callback/monitor path until inline exclusives are requalified on PS5 hardware.
    option(EDEN_INLINE_EXCLUSIVES "Inline page-table exclusive accesses" OFF)
    if(EDEN_INLINE_EXCLUSIVES)
        foreach(spacing "  " " ")
            string(REPLACE "config.fastmem_exclusive_access = config.fastmem_pointer${spacing}!= std::nullopt;"
                "config.fastmem_exclusive_access = true;" wrapper "${wrapper}")
        endforeach()
        string(FIND "${wrapper}" "config.fastmem_exclusive_access = true;" inline_exclusive_at)
        if(inline_exclusive_at LESS 0)
            message(FATAL_ERROR "Pinned exclusive-access configuration changed")
        endif()
    endif()
      string(REPLACE "std::uint32_t(512_MiB)" "std::uint32_t(16_MiB)" wrapper "${wrapper}")
      # The same dynamic physical headroom policy applies to every A64/A32
      # title. Guest code capacity is chosen once, before core construction.
      # Core 3/host keep 16 MiB. Both guest ISAs are not active together.
      if(PS5_NATIVE)
          if(bits EQUAL 64)
              set(jit_cache_sizes "::Eden::Experimental::A64CacheBytes(m_core_index, m_core_index == 0 ? 256_MiB : m_core_index < 3 ? 192_MiB : 16_MiB)")
          else()
              set(jit_cache_sizes "::Eden::Experimental::A32CacheBytes(m_core_index, m_core_index == 0 ? 512_MiB : m_core_index < 3 ? 64_MiB : 16_MiB)")
          endif()
          string(REPLACE "std::uint32_t(16_MiB)" "std::uint32_t(${jit_cache_sizes})" wrapper "${wrapper}")
          string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/experimental_performance.h\"\n")
      endif()
    set(derived "${PORT_BUILD_DIR}/arm_dynarmic_${bits}.cpp")
    # JIT entry/exit sampling is diagnostic instrumentation, not a shipping feature.
    # Keep all atomics, clocks and profiler calls out of the release hot path.
    if(EDEN_DEV_PROFILE)
        string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/performance.h\"\n")
        if(bits EQUAL 64)
            set(sample_pc "m_jit->GetPC()")
            set(sample_fp "m_jit->GetFpcr()")
        else()
            set(sample_pc "m_jit->Regs()[15]")
            set(sample_fp "m_jit->Fpscr()")
        endif()
        string(REPLACE "    return TranslateHaltReason(m_jit->Run());"
            "    const bool eden_detailed_cpu_sample = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed);\n    if (eden_detailed_cpu_sample && ::Eden::Performance::CpuSampleDue(m_core_index)) ::Eden::Performance::SampleCpu(m_core_index, Kernel::GetCurrentThread(m_system.Kernel()).GetThreadId(), ${sample_pc}, GetSvcNumber(), ${sample_fp});\n    ::Eden::Performance::cpu_state[m_core_index].phase.store(::Eden::Performance::CpuPhase::Guest, std::memory_order_release);\n    const auto halt = m_jit->Run();\n    ::Eden::Performance::cpu_state[m_core_index].phase.store(::Eden::Performance::CpuPhase::Kernel, std::memory_order_release);\n    if (eden_detailed_cpu_sample && ::Eden::Performance::CpuSampleDue(m_core_index)) ::Eden::Performance::SampleCpu(m_core_index, Kernel::GetCurrentThread(m_system.Kernel()).GetThreadId(), ${sample_pc}, GetSvcNumber(), ${sample_fp});\n    return TranslateHaltReason(halt);"
            wrapper "${wrapper}")
    endif()
    if(EDEN_DEV_PROFILE)
        if(bits EQUAL 32)
            string(REPLACE "u8 DynarmicCallbacks32::MemoryRead8(u32 vaddr) {"
                "u8 DynarmicCallbacks32::MemoryRead8(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "u16 DynarmicCallbacks32::MemoryRead16(u32 vaddr) {"
                "u16 DynarmicCallbacks32::MemoryRead16(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "u32 DynarmicCallbacks32::MemoryRead32(u32 vaddr) {"
                "u32 DynarmicCallbacks32::MemoryRead32(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "u64 DynarmicCallbacks32::MemoryRead64(u32 vaddr) {"
                "u64 DynarmicCallbacks32::MemoryRead64(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite8(u32 vaddr, u8 value) {"
                "void DynarmicCallbacks32::MemoryWrite8(u32 vaddr, u8 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite16(u32 vaddr, u16 value) {"
                "void DynarmicCallbacks32::MemoryWrite16(u32 vaddr, u16 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite32(u32 vaddr, u32 value) {"
                "void DynarmicCallbacks32::MemoryWrite32(u32 vaddr, u32 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite64(u32 vaddr, u64 value) {"
                "void DynarmicCallbacks32::MemoryWrite64(u32 vaddr, u64 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive8(u32 vaddr, u8 value, u8 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive8(u32 vaddr, u8 value, u8 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive16(u32 vaddr, u16 value, u16 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive16(u32 vaddr, u16 value, u16 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive32(u32 vaddr, u32 value, u32 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive32(u32 vaddr, u32 value, u32 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive64(u32 vaddr, u64 value, u64 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive64(u32 vaddr, u64 value, u64 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
        endif()
        string(REPLACE "    m_jit.emplace(config);"
            "    std::printf(\"EDEN_DEV_JIT bits=${bits} core=%zu cache=%u\\n\", m_core_index, config.code_cache_size);\n    m_jit.emplace(config);"
            wrapper "${wrapper}")
        if(bits EQUAL 64)
            # Guest calls through null pointers (seen in a boot race):
            # dump the guest code around the return chain for offline disassembly.
            set(no_execute "        LOG_CRITICAL(Core_ARM, \"Cannot execute instruction at unmapped address {:#016x}\", pc);\n")
            string(FIND "${wrapper}" "${no_execute}" no_execute_at)
            if(no_execute_at LESS 0)
                message(FATAL_ERROR "Pinned no-execute fault handler changed")
            endif()
            string(REPLACE "${no_execute}" "${no_execute}        ::Eden::CrashSite::Dump(m_memory, *m_parent.m_jit);\n        ::Eden::CrashSite::DumpThreads(\"fault\", *m_process);\n"
                wrapper "${wrapper}")
            string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/crash_site.h\"\n")
            # dev-settings watch=: writes into the watched range reach these callbacks (its
            # pages are marked debug) and are reported with the guest thread (watch.h).
            set(watch_context "m_memory, *m_parent.m_jit, Kernel::GetCurrentThread(m_parent.m_system.Kernel()), m_parent.m_core_index")
            foreach(write IN ITEMS "MemoryWrite8(u64 vaddr, u8 value)|1|value" "MemoryWrite16(u64 vaddr, u16 value)|2|value"
                    "MemoryWrite32(u64 vaddr, u32 value)|4|value" "MemoryWrite64(u64 vaddr, u64 value)|8|value"
                    "MemoryWrite128(u64 vaddr, Dynarmic::A64::Vector value)|16|value[0]"
                    "MemoryWriteExclusive8(u64 vaddr, std::uint8_t value, std::uint8_t expected)|1|value"
                    "MemoryWriteExclusive16(u64 vaddr, std::uint16_t value, std::uint16_t expected)|2|value"
                    "MemoryWriteExclusive32(u64 vaddr, std::uint32_t value, std::uint32_t expected)|4|value"
                    "MemoryWriteExclusive64(u64 vaddr, std::uint64_t value, std::uint64_t expected)|8|value"
                    "MemoryWriteExclusive128(u64 vaddr, Dynarmic::A64::Vector value, Dynarmic::A64::Vector expected)|16|value[0]")
                string(REPLACE "|" ";" write_parts "${write}")
                list(GET write_parts 0 write_signature)
                list(GET write_parts 1 write_size)
                list(GET write_parts 2 write_value)
                set(write_head "DynarmicCallbacks64::${write_signature} {\n")
                string(FIND "${wrapper}" "${write_head}" write_at)
                if(write_at LESS 0)
                    message(FATAL_ERROR "Pinned A64 write callback changed: ${write_signature}")
                endif()
                string(REPLACE "${write_head}"
                    "${write_head}    if (::Eden::Watch::Hit(vaddr, ${write_size})) ::Eden::Watch::Report(vaddr, ${write_size}, u64(${write_value}), ${watch_context});\n"
                    wrapper "${wrapper}")
            endforeach()
            string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/watch.h\"\n#include \"core/hle/kernel/k_thread.h\"\n#include \"core/hle/kernel/kernel.h\"\n")
        endif()
    endif()
    if(PS5_NATIVE)
        # Do not silently lose a game when a dynamically sized code arena
        # cannot be allocated contiguously. Retry only allocator errors at
        # smaller capacities down to the old qualified per-core baseline.
        # The 8 MiB null-JIT path is intentionally left untouched.
        set(jit_init_site "    m_jit.emplace(config);")
        string(FIND "${wrapper}" "${jit_init_site}" jit_init_at)
        if(jit_init_at LESS 0)
            message(FATAL_ERROR "Pinned Dynarmic guest JIT construction changed")
        endif()
        if(bits EQUAL 64)
            set(jit_legacy_baseline "::Eden::Experimental::kA64Baseline[m_core_index]")
        else()
            set(jit_legacy_baseline "::Eden::Experimental::kA32Baseline[m_core_index]")
        endif()
        string(REPLACE "${jit_init_site}"
            "    ::Eden::JitStartup::ConstructWithCapacityFallback(\n        config.code_cache_size, ${jit_legacy_baseline}, ${bits}, m_core_index,\n        [&]() { m_jit.emplace(config); });"
            wrapper "${wrapper}")
        string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/jit-startup-retry.h\"\n")
    endif()
    # Native guest callbacks must not read RAM after abort/watchpoint refusal.
    if(PS5_NATIVE)
        include("${EDEN_PORT_DIR}/native_jit_memory_read_guard.cmake")
    endif()
    write_derived("${derived}" "#include <bit>\n${wrapper}")
    list(REMOVE_ITEM core_sources "${relative}")
    list(APPEND core_sources "${derived}")
endforeach()
# A prefetch abort (guest jump to an unmapped address) parks the thread for a debugger; with
# none attached, record it so the frontend ends the session instead of showing a black screen
# forever (headless/guest_fault.h).
file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/physical_core.cpp" physical_core_source)
set(prefetch_old "            } else {\n                interface->LogBacktrace(process);\n            }\n            thread->RequestSuspend(kernel, SuspendType::Debug);")
string(FIND "${physical_core_source}" "${prefetch_old}" prefetch_at)
if(prefetch_at LESS 0)
    message(FATAL_ERROR "Pinned prefetch-abort handling changed")
endif()
# Guest core idle: count each wait and how long it lasted, and spin on the
# interrupt flag for a bounded time before sleeping on the condition variable, because waking a
# sleeping host thread puts the host scheduler's latency on the guest's critical path.
set(idle_old "void PhysicalCore::Idle() {\n    std::unique_lock lk{m_guard};\n    m_on_interrupt.wait(lk, [this] { return m_is_interrupted; });\n}")
string(FIND "${physical_core_source}" "${idle_old}" idle_at)
if(idle_at LESS 0)
    message(FATAL_ERROR "Pinned PhysicalCore::Idle changed")
endif()
# Keep Eden's exact mutex/condition-variable idle path in shipping builds.
# Profiling annotations and experimental spin-before-sleep exist only in diagnostic builds.
if(EDEN_DEV_PROFILE)
    string(REPLACE "${idle_old}" [=[void PhysicalCore::Idle() {
        const bool profile_idle = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed);
        const long long start = profile_idle ? ::Eden::Performance::NowNs() : 0;
        // The interrupt flag is guarded by m_guard. An unlocked atomic
        // builtin read races with Interrupt()/ClearInterrupt() plain stores.
        // Diagnostic idle sampling uses the original condition variable.
        bool slept;
        {
            std::unique_lock lk{m_guard};
            slept = !m_is_interrupted;
            m_on_interrupt.wait(lk, [this] { return m_is_interrupted; });
        }
        if (profile_idle)
            ::Eden::Performance::CountIdle(m_core_index, ::Eden::Performance::NowNs() - start, slept);
    }]=] physical_core_source "${physical_core_source}")
endif()
string(REPLACE "${prefetch_old}" [=[            } else {
                interface->LogBacktrace(process);
                if (prefetch_abort) {
                    // ExitContext saves guest registers only for attached debuggers.
                    // Capture the faulting PC at the actual prefetch abort before
                    // the suspended thread can be unloaded or switched.
                    interface->GetContext(thread->GetContext());
                    const auto eden_name = Core::GetThreadName(thread).value_or("?");
                    // A faulting PC alone cannot identify a corrupt
                    // indirect-branch target vs a stale JIT return. Preserve
                    // the original guest return address and stack registers
                    // on this single fatal path; never sample per-frame.
                    const auto& fault_context = thread->GetContext();
                    // One bounded page-table query at the fatal fault only.
                    // Never dereference an untrusted guest address or alter JIT.
                    Kernel::KMemoryInfo lr_info{};
                    Kernel::Svc::PageInfo lr_page{};
                    const bool lr_query = process &&
                        !process->GetPageTable().QueryInfo(
                            &lr_info, &lr_page, fault_context.lr).IsError();
                    std::fprintf(stderr,
                        "EDEN_GUEST_FAULT_LR_MAP lr=0x%llx query=%s start=0x%llx size=0x%llx state=%u\n",
                        static_cast<unsigned long long>(fault_context.lr),
                        lr_query ? "ok" : "failed",
                        static_cast<unsigned long long>(lr_info.m_address),
                        static_cast<unsigned long long>(lr_info.m_size),
                        static_cast<unsigned>(lr_info.m_state));
                    char eden_fault[320]{};
                    std::snprintf(eden_fault, sizeof(eden_fault),
                        "guest thread %.64s tid=%llu pc=0x%llx lr=0x%llx sp=0x%llx fp=0x%llx jumped to an unmapped address",
                        eden_name.c_str(),
                        static_cast<unsigned long long>(thread->GetThreadId()),
                        static_cast<unsigned long long>(fault_context.pc),
                        static_cast<unsigned long long>(fault_context.lr),
                        static_cast<unsigned long long>(fault_context.sp),
                        static_cast<unsigned long long>(fault_context.fp));
                    ::Eden::RecordGuestFault(eden_fault);
                }
            }
            thread->RequestSuspend(kernel, SuspendType::Debug);]=]
    physical_core_source "${physical_core_source}")
include("${CMAKE_CURRENT_LIST_DIR}/physical_core_interrupt_atomic.cmake")
write_derived("${PORT_BUILD_DIR}/physical_core.cpp"
    "#include <cstdio>\n#include \"${EDEN_PORT_DIR}/guest_fault.h\"\n#include \"${EDEN_PORT_DIR}/performance.h\"\n#include \"core/hle/kernel/k_process.h\"\n#include \"core/arm/debug.h\"\n${physical_core_source}")
list(REMOVE_ITEM core_sources "hle/kernel/physical_core.cpp")
list(APPEND core_sources "${PORT_BUILD_DIR}/physical_core.cpp")
# Guest scheduler spin lock is maintained as a complete qualified source, not a CMake rewrite.
set(eden_kernel_spin "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/kernel/k_spin_lock.cpp")
if(NOT EXISTS "${eden_kernel_spin}")
    message(FATAL_ERROR "Missing maintained guest scheduler lock source")
endif()
target_include_directories(core PRIVATE "${EDEN_PORT_DIR}")
list(REMOVE_ITEM core_sources "hle/kernel/k_spin_lock.cpp")
list(APPEND core_sources "${eden_kernel_spin}")
if(EDEN_DEV_PROFILE)
    # Guest-visible waits: syncpoint event registration to signal (GPU-pipeline latency
    # the game waits on) and buffer-queue dequeue waits (presentation back-pressure).
    # Host-syncpoint event-wait diagnostics are maintained C++ (DEV only).
    # Selecting a tracked source is preferable to generating code at configure time.
    set(EDEN_MAINTAINED_PROFILE_NVCTRL
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/nvdrv/devices/nvhost_ctrl.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_NVCTRL}")
        message(FATAL_ERROR "Missing maintained nvhost_ctrl profile source")
    endif()
    list(REMOVE_ITEM core_sources "hle/service/nvdrv/devices/nvhost_ctrl.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_NVCTRL}")
    # DEV-only buffer dequeue timing comes from a tracked maintained TU.
    set(EDEN_MAINTAINED_PROFILE_DEQUEUE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_DEQUEUE}")
        message(FATAL_ERROR "Missing maintained buffer queue diagnostic source")
    endif()
    list(REMOVE_ITEM core_sources "hle/service/nvnflinger/buffer_queue_producer.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_DEQUEUE}")
    # Guest asset streaming: time and bytes of fsp-srv IFile/IStorage backend reads.
    # Use the reviewed, maintained source directly. The original source stays
    # pinned; no C++ text replacement or generated translation unit in CMake.
    set(EDEN_MAINTAINED_PROFILE_FS_FILE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/filesystem/fsp/fs_i_file.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_FS_FILE}")
        message(FATAL_ERROR "Missing maintained IFile profile source")
    endif()
    list(REMOVE_ITEM core_sources "hle/service/filesystem/fsp/fs_i_file.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_FS_FILE}")
    # Maintained version of the previously generated IStorage::Read witness.
    set(EDEN_MAINTAINED_PROFILE_FS_STORAGE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/filesystem/fsp/fs_i_storage.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_FS_STORAGE}")
        message(FATAL_ERROR "Missing maintained IStorage profile source")
    endif()
    # DEV profile: use the maintained filesystem-open diagnostics directly.
    # No configure-time C++ text rewriting; pinned dependency stays immutable.
    set(EDEN_MAINTAINED_PROFILE_FS_SYSTEM
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/filesystem/fsp/fs_i_filesystem.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_FS_SYSTEM}")
        message(FATAL_ERROR "Missing maintained IFileSystem profile source")
    endif()
    list(REMOVE_ITEM core_sources "hle/service/filesystem/fsp/fs_i_filesystem.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_FS_SYSTEM}")
    list(REMOVE_ITEM core_sources "hle/service/filesystem/fsp/fs_i_storage.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_FS_STORAGE}")
    # DEV-only HLE service/IPC diagnostics: select maintained translation units,
    # never edit pinned upstream C++ using configure-time text replacements.
    set(EDEN_MAINTAINED_PROFILE_HLE_SERVICE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/service.cpp")
    set(EDEN_MAINTAINED_PROFILE_SVC_IPC
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/kernel/svc/svc_ipc.cpp")
    foreach(maintained_source IN ITEMS
            "${EDEN_MAINTAINED_PROFILE_HLE_SERVICE}" "${EDEN_MAINTAINED_PROFILE_SVC_IPC}")
        if(NOT EXISTS "${maintained_source}")
            message(FATAL_ERROR "Missing maintained HLE/IPC DEV source: ${maintained_source}")
        endif()
    endforeach()
    list(REMOVE_ITEM core_sources "hle/service/service.cpp" "hle/kernel/svc/svc_ipc.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_HLE_SERVICE}"
                             "${EDEN_MAINTAINED_PROFILE_SVC_IPC}")
endif()
if(EDEN_A32_FASTMEM)
    # The window spans 4 GiB: only 32-bit applications get it as their fastmem arena.
    # The production backport materializes core/memory.cpp before configure.
    # Maintain the native A32-only fastmem guard as versioned C++, not a
    # configure-time rewrite of that materialized source.
    set(EDEN_MAINTAINED_A32_MEMORY
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/memory.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_A32_MEMORY}")
        message(FATAL_ERROR "Missing maintained A32 fastmem memory source")
    endif()
    list(REMOVE_ITEM core_sources "memory.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_A32_MEMORY}")
    # Upstream places code at any 4 KiB offset below 16 MiB, which leaves three of four
    # layouts with every module page out of 16 KiB phase with its backing. Keep the same
    # range with 16 KiB steps so module chunks can alias.
    set(EDEN_MAINTAINED_CODE_LOADER
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/loader/deconstructed_rom_directory.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_CODE_LOADER}")
        message(FATAL_ERROR "Missing maintained aligned code loader")
    endif()
    list(REMOVE_ITEM core_sources "loader/deconstructed_rom_directory.cpp")
    list(APPEND core_sources "${EDEN_MAINTAINED_CODE_LOADER}")
endif()
set_property(TARGET core PROPERTY SOURCES "${core_sources}")
# The guest title is the owner of a zero-ID cache storage request.
set(EDEN_MAINTAINED_SAVEDATA
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/file_sys/savedata_factory.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_SAVEDATA}")
    message(FATAL_ERROR "Missing maintained per-title cache storage source")
endif()
get_target_property(eden_savedata_sources core SOURCES)
list(REMOVE_ITEM eden_savedata_sources "file_sys/savedata_factory.cpp")
list(APPEND eden_savedata_sources "${EDEN_MAINTAINED_SAVEDATA}")
set_property(TARGET core PROPERTY SOURCES "${eden_savedata_sources}")
# Use a maintained bounded shader local-memory translator, keeping the pinned source untouched.
set(EDEN_MAINTAINED_SHADER_LOCAL
    "${PORT_ROOT}/vendor/encore-active/eden-shader/src/shader_recompiler/frontend/maxwell/translate/impl/load_store_local_shared.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_SHADER_LOCAL}")
    message(FATAL_ERROR "Missing maintained shader local scratch translator")
endif()
get_target_property(eden_shader_sources shader_recompiler SOURCES)
list(FIND eden_shader_sources "frontend/maxwell/translate/impl/load_store_local_shared.cpp" eden_shader_local_position)
if(eden_shader_local_position LESS 0)
    message(FATAL_ERROR "Pinned shader local translator target changed")
endif()
list(REMOVE_ITEM eden_shader_sources "frontend/maxwell/translate/impl/load_store_local_shared.cpp")
list(APPEND eden_shader_sources "${EDEN_MAINTAINED_SHADER_LOCAL}")
set_property(TARGET shader_recompiler PROPERTY SOURCES "${eden_shader_sources}")
# PS5_NATIVE is a CMake option, not a transitive preprocessor definition for
# core or video_core. Only these two pinned TUs own the address guards below.
# Do NOT enable it broadly for every upstream C++ source.
if(PS5_NATIVE)
    # Keep the pinned collector source immutable. The maintained header fixes
    # an atomic page-transition race only for the native target. Make this
    # sole-header override PUBLIC so consumers share one inline definition.
    set(EDEN_NATIVE_DIRTY_HEADER_ROOT
        "${PORT_ROOT}/vendor/encore-active/eden-core/overrides")
    if(NOT EXISTS "${EDEN_NATIVE_DIRTY_HEADER_ROOT}/core/gpu_dirty_memory_manager.h")
        message(FATAL_ERROR "Missing maintained native GPU dirty collector")
    endif()
    # Override the immutable shipping guest policy on native builds without
    # changing the backport manifest or the host launcher's network clients.
    if(NOT EXISTS "${EDEN_NATIVE_DIRTY_HEADER_ROOT}/core/hle/service/sockets/encore_guest_network_policy.h")
        message(FATAL_ERROR "Missing maintained native guest offline policy")
    endif()
    target_include_directories(core BEFORE PUBLIC "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")
    # The native guest-memory header is shared by core and video_core.
    # The latter instantiates GPU write-back templates in its own TUs.
    if(NOT EXISTS "${EDEN_NATIVE_DIRTY_HEADER_ROOT}/core/guest_memory.h")
        message(FATAL_ERROR "Missing maintained native guest memory bounds")
    endif()
    # The native device-memory instantiation must discard stale contiguous
    # mapping metadata on Unmap and default (untracked) Map. Source-only
    # consumers keep the pinned upstream implementation.
    if(NOT EXISTS "${EDEN_NATIVE_DIRTY_HEADER_ROOT}/core/device_memory_manager.inc")
        message(FATAL_ERROR "Missing maintained native device memory continuity")
    endif()
    target_include_directories(video_core BEFORE PRIVATE "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")
    if(EDEN_A32_FASTMEM)
        set(eden_cpu_memory_tu "${PORT_BUILD_DIR}/memory.cpp")
    else()
        set(eden_cpu_memory_tu "${PROJECT_SOURCE_DIR}/src/core/memory.cpp")
    endif()
    # The native console exhibited 38,472 unmapped memory error lines within
    # 1.1 seconds shortly before FC27's halftime crash. Preserve the first
    # 64 full errors and power-of-two followups, without mutating guest memory.
    # Keep the upstream TU immutable and compose with the optional A32 port.
    file(READ "${eden_cpu_memory_tu}" eden_cpu_memory)
    set(unmapped_log "LOG_ERROR(HW_Memory, \"Unmapped ")
    string(FIND "${eden_cpu_memory}" "${unmapped_log}" unmapped_at)
    if(unmapped_at LESS 0)
        message(FATAL_ERROR "Pinned unmapped memory error diagnostics changed")
    endif()
    string(REPLACE "${unmapped_log}"
        "if (::Eden::Performance::ShouldLogUnmappedAccess()) LOG_ERROR(HW_Memory, \"Unmapped "
        eden_cpu_memory "${eden_cpu_memory}")
    # There are 11 error sites in the pinned memory.cpp; fail closed if upstream
    # changes the count instead of silently leaving one path unbounded.
    string(REGEX MATCHALL "ShouldLogUnmappedAccess\\(\\)" unmapped_calls "${eden_cpu_memory}")
    list(LENGTH unmapped_calls unmapped_count)
    if(NOT unmapped_count EQUAL 11)
        message(FATAL_ERROR "Pinned unmapped memory error sites changed: ${unmapped_count} != 11")
    endif()
    # Native guest CPU reads can also be requested from auxiliary host threads.
    # Their TLS host ID is outside the four guest-core array slots. Never
    # use that ID to index rasterizer_read_areas or share mapping scratch
    # with the GPU-owner/system-core write paths. Avoid a lock over a GPU
    # read fence: keep the normal guest-core read-area cache unchanged.
    set(eden_read_original [=[
        const size_t core = system.GetCurrentHostThreadID();
        auto& current_area = rasterizer_read_areas[core];
        gpu_device_memory->ApplyOpOnPointer(p, scratch_buffers[core], [&](DAddr address) {]=])
    set(eden_read_native [=[
        const size_t host_core = system.GetCurrentHostThreadID();
        thread_local Common::ScratchBuffer<u32> read_scratch;
        VideoCore::RasterizerDownloadArea auxiliary_read_area{};
        auto& current_area = host_core < Core::Hardware::NUM_CPU_CORES
            ? rasterizer_read_areas[host_core] : auxiliary_read_area;
        gpu_device_memory->ApplyOpOnPointer(p, read_scratch, [&](DAddr address) {]=])
    string(FIND "${eden_cpu_memory}" "${eden_read_original}" eden_read_position)
    if(eden_read_position LESS 0)
        message(FATAL_ERROR "Pinned native guest CPU read scratch/slot contract changed")
    endif()
    string(REPLACE "${eden_read_original}" "${eden_read_native}"
        eden_cpu_memory "${eden_cpu_memory}")
    # GPUDirtyMemoryManager::BuildTransform has a 32-bit mask of 64-byte
    # cells (2 KiB). HandleRasterizerWrite may pass a whole 4 KiB page.
    # Split before Collect, keeping the vendored code unchanged.
    set(eden_dirty_raw "            gpu_dirty_managers[core].Collect(address, size);")
    string(FIND "${eden_cpu_memory}" "${eden_dirty_raw}" eden_dirty_at)
    if(eden_dirty_at LESS 0)
        message(FATAL_ERROR "Pinned native GPUDirty Collect call changed")
    endif()
    string(REPLACE "${eden_dirty_raw}" [=[
            ::Eden::GpuDirty::ForEachRegion(address, size,
                [&](std::uint64_t subaddress, std::uint64_t span) {
                    gpu_dirty_managers[core].Collect(subaddress, span);
                });]=] eden_cpu_memory "${eden_cpu_memory}")
    string(PREPEND eden_cpu_memory "#include \"${EDEN_PORT_DIR}/gpu_dirty_region_split.h\"\n")
    # Guest spans end at addr + size - 1, not at addr + size.
    # The pinned expression reads one page too far on exact boundaries,
    # including one-past-end of the guest page table. Apply only to the
    # already-derived native memory translation unit.
    set(eden_span_original [=[        return (current_page_table->entries[addr >> YUZU_PAGEBITS].Block() == current_page_table->entries[(addr + size) >> YUZU_PAGEBITS].Block()) ? GetPointerSilent(addr) : nullptr;]=])
    string(REGEX MATCHALL "GetPointerSilent\\(addr\\) : nullptr;" eden_span_calls "${eden_cpu_memory}")
    list(LENGTH eden_span_calls eden_span_count)
    if(NOT eden_span_count EQUAL 2)
        message(FATAL_ERROR "Pinned native guest span page-boundary contract changed")
    endif()
    string(REPLACE "${eden_span_original}" [=[        if (size == 0 || addr + (size - 1) < addr) {
            return nullptr;
        }
        const auto start_page = addr >> YUZU_PAGEBITS;
        const auto end_page = (addr + size - 1) >> YUZU_PAGEBITS;
        const auto& entries = current_page_table->entries;
        if (start_page >= entries.size() || end_page >= entries.size()) {
            return nullptr;
        }
        return entries[start_page].Block() == entries[end_page].Block()
            ? GetPointerSilent(addr) : nullptr;]=] eden_cpu_memory "${eden_cpu_memory}")
    # Bound guest range arithmetic in the already-generated native memory TU.
    # A wrapped end can otherwise let an invalid address range pass unchecked.
    include("${EDEN_PORT_DIR}/native_guest_range_overflow.cmake")
    set(eden_native_memory_tu "${PORT_BUILD_DIR}/memory-ps5.cpp")
    write_derived("${eden_native_memory_tu}"
        "#include \"${EDEN_PORT_DIR}/performance.h\"\n${eden_cpu_memory}")
    if(EDEN_A32_FASTMEM)
        list(REMOVE_ITEM core_sources "${PORT_BUILD_DIR}/memory.cpp")
    else()
        list(REMOVE_ITEM core_sources "memory.cpp")
    endif()
    list(APPEND core_sources "${eden_native_memory_tu}")
    set_property(TARGET core PROPERTY SOURCES "${core_sources}")
    set_property(SOURCE "${eden_native_memory_tu}" TARGET_DIRECTORY core
        APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1")
    set_property(SOURCE "${PROJECT_SOURCE_DIR}/src/video_core/host1x/gpu_device_memory_manager.cpp"
        TARGET_DIRECTORY video_core APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1")
    # Upstream core is a distinct static target: PS5_NATIVE on eden-headless
    # does NOT propagate here. Disable Switch HOME/Capture applet behavior
    # only in the pinned AM poller, leaving desktop behavior unchanged.
    set_property(SOURCE "${PROJECT_SOURCE_DIR}/src/core/hle/service/am/button_poller.cpp"
        TARGET_DIRECTORY core APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1")
endif()
# Maintained service source: title metadata null handling plus a dev-only
# witness of the version resolved from guest update content.
set(EDEN_APP_FUNCTION_SOURCE "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/am/service/application_functions.cpp")
if(NOT EXISTS "${EDEN_APP_FUNCTION_SOURCE}")
    message(FATAL_ERROR "Missing maintained guest application metadata service")
endif()
list(FIND core_sources "hle/service/am/service/application_functions.cpp" eden_app_old)
if(eden_app_old EQUAL -1)
    message(FATAL_ERROR "Pinned application metadata service source moved")
endif()
list(REMOVE_ITEM core_sources "hle/service/am/service/application_functions.cpp")
list(APPEND core_sources "${EDEN_APP_FUNCTION_SOURCE}")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")
if(PS5_NATIVE AND EDEN_DEV_PROFILE)
    target_compile_definitions(core PRIVATE EDEN_GUEST_TITLE_VERSION_DIAG=1)
endif()
# Core's NS query service owns this implementation from frontend_common.
target_sources(core PRIVATE "${PROJECT_SOURCE_DIR}/src/frontend_common/play_time_manager.cpp")

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
get_target_property(core_sources core SOURCES)
# The PS5 heap is bounded: avoid allocating/decompressing an executable merely
# to calculate its layout, and avoid vector growth duplicating a large BSS image.
if(PS5_NATIVE)
    file(READ "${PROJECT_SOURCE_DIR}/src/core/loader/nso.cpp" nso_source)
    set(old_nso_image "    Kernel::CodeSet codeset;\n    codeset.memory.resize(module_start + last_segment_it->location + last_segment_it->size);")
    set(new_nso_image [=[    const u64 initialized_size = module_start + u64(last_segment_it->location) + u64(last_segment_it->size);
    const u64 argument_size = should_pass_arguments && !Settings::values.program_args.GetValue().empty()
        ? NSO_ARGUMENT_DATA_ALLOCATION_SIZE : 0;
    const u64 final_size = (initialized_size + argument_size + u64(last_segment_it->bss_size) + 0xFFF) & ~u64(0xFFF);
    if (!final_size || final_size > UINT32_MAX) return std::nullopt;
    for (size_t i = 0; i < nso_header.segments.size(); ++i) {
        const auto& segment = nso_header.segments[i];
        const u64 stored_size = nso_header.IsSegmentCompressed(i)
            ? u64(nso_header.segments_compressed_size[i]) : u64(segment.size);
        if ((nso_header.IsSegmentCompressed(i) && (stored_size > INT32_MAX || u64(segment.size) > INT32_MAX)) ||
            u64(segment.offset) + stored_size > nso_file.GetSize() ||
            module_start + u64(segment.location) + u64(segment.size) > initialized_size)
            return std::nullopt;
    }
    // PS5 uses Dynarmic, not NCE: a layout query needs no executable bytes.
#ifdef HAS_NCE
#error Review PS5 NSO layout-only loading before enabling NCE
#endif
    if (!load_into_process) return load_base + final_size;
    std::fprintf(stderr, "[ProsperoEden] NSO %s image_bytes=%llu bss_bytes=%u\n",
                 nso_file.GetName().c_str(), static_cast<unsigned long long>(final_size),
                 static_cast<unsigned>(last_segment_it->bss_size));
    Kernel::CodeSet codeset;
    const auto name = nso_file.GetName();
    // A mod's patch changes code and data, which are here whole; only a dump wants the BSS too.
    const bool patched = pm && pm->HasNSOPatch(nso_header.build_id, name);
    const bool full_image = pm && Settings::values.dump_nso;
    // BSS belongs in guest memory, not a second almost-2-GiB heap buffer.
    codeset.memory.reserve(full_image ? final_size : initialized_size + argument_size);
    codeset.memory.resize(initialized_size);]=])
    string(FIND "${nso_source}" "${old_nso_image}" nso_offset)
    if(nso_offset LESS 0)
        message(FATAL_ERROR "Pinned NSO loader changed")
    endif()
    string(REPLACE "${old_nso_image}" "${new_nso_image}" nso_source "${nso_source}")
    string(REPLACE "    codeset.memory.resize(image_size);" "    if (full_image) codeset.memory.resize(image_size);" nso_source "${nso_source}")
    string(REPLACE "    const auto name = nso_file.GetName();\n    if (pm && (pm->HasNSOPatch(nso_header.build_id, name) || Settings::values.dump_nso)) {"
        "    if (patched || full_image) {" nso_source "${nso_source}")
    string(REPLACE "    // Load codeset for current process"
        "    // Initialize BSS and page padding directly, including reused guest pages.\n    if (codeset.memory.size() < image_size &&\n        !process.GetMemory().ZeroBlock(load_base + codeset.memory.size(), image_size - codeset.memory.size()))\n        return std::nullopt;\n\n    // Load codeset for current process" nso_source "${nso_source}")
    set(old_nso_decode [=[        std::vector<u8> decompressed_size(std::ranges::max_element(nso_header.segments, [](auto const& a, auto const& b) {
            return a.size < b.size;
        })->size);]=])
    string(REPLACE "${old_nso_decode}" "" nso_source "${nso_source}")
    string(REPLACE "            nso_file.Read(compressed_data.data(), nso_header.segments_compressed_size[i], nso_header.segments[i].offset);"
        "            auto* destination = codeset.memory.data() + module_start + nso_header.segments[i].location;\n            if (!nso_header.IsSegmentCompressed(i)) {\n                if (nso_file.Read(destination, nso_header.segments[i].size, nso_header.segments[i].offset) != nso_header.segments[i].size) return std::nullopt;\n            } else if (nso_file.Read(compressed_data.data(), nso_header.segments_compressed_size[i], nso_header.segments[i].offset) != nso_header.segments_compressed_size[i]) return std::nullopt;"
        nso_source "${nso_source}")
    set(old_nso_decompress [=[                int r = Common::Compression::DecompressDataLZ4(decompressed_size.data(), nso_header.segments[i].size, compressed_data.data(), nso_header.segments_compressed_size[i]);
                ASSERT(r == int(nso_header.segments[i].size));]=])
    set(new_nso_decompress [=[                int r = -1;
                if ((nso_header.flags >> 7) & 1) {
                    r = Common::Compression::DecompressDataZBIC(
                        std::span<u8>{destination, nso_header.segments[i].size},
                        std::span<const u8>{compressed_data.data(), nso_header.segments_compressed_size[i]});
                } else {
                    r = Common::Compression::DecompressDataLZ4(
                        destination, nso_header.segments[i].size,
                        compressed_data.data(), nso_header.segments_compressed_size[i]);
                }
                if (r != int(nso_header.segments[i].size)) return std::nullopt;]=])
    string(FIND "${nso_source}" "${old_nso_decompress}" nso_decompress_offset)
    if(nso_decompress_offset LESS 0)
        message(FATAL_ERROR "Pinned NSO decompression block changed")
    endif()
    string(REPLACE "${old_nso_decompress}" "${new_nso_decompress}" nso_source "${nso_source}")
    string(REPLACE "                std::memcpy(codeset.memory.data() + module_start + nso_header.segments[i].location, decompressed_size.data(), nso_header.segments[i].size);" "" nso_source "${nso_source}")
    string(REPLACE "            } else {\n                std::memcpy(codeset.memory.data() + module_start + nso_header.segments[i].location, compressed_data.data(), nso_header.segments[i].size);" "" nso_source "${nso_source}")
    string(PREPEND nso_source "#include <cstdio>\n#include <span>\n#include \"zbic_compression.h\"\n")
    write_derived("${PORT_BUILD_DIR}/nso.cpp" "${nso_source}")
    list(REMOVE_ITEM core_sources loader/nso.cpp)
    list(APPEND core_sources "${PORT_BUILD_DIR}/nso.cpp")
endif()
list(REMOVE_ITEM core_sources core.cpp)
list(APPEND core_sources "${PORT_BUILD_DIR}/core.cpp")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")

# RomFS builder parents are non-owning: the tracked source retains both
# original shared_ptr-to-pointer replacements without CMake rewriting.
set(EDEN_MAINTAINED_ROMFS_BUILDER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/file_sys/fsmitm_romfsbuild.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_ROMFS_BUILDER}")
    message(FATAL_ERROR "Missing maintained RomFS builder source")
endif()
get_target_property(core_sources core SOURCES)
list(REMOVE_ITEM core_sources file_sys/fsmitm_romfsbuild.cpp)
list(APPEND core_sources "${EDEN_MAINTAINED_ROMFS_BUILDER}")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")

# One change to a pinned Eden source; the build stops when the text it replaces is gone.
function(eden_patch source old new)
    string(FIND "${${source}}" "${old}" patch_at)
    if(patch_at LESS 0)
        message(FATAL_ERROR "Pinned Eden source changed; not found: ${old}")
    endif()
    string(REPLACE "${old}" "${new}" patched "${${source}}")
    set(${source} "${patched}" PARENT_SCOPE)
endfunction()

# Mods (headless/mods.h). The pinned patch code cannot apply an .ips patch (it looks for the
# patch's magic in the game's code, and its end marker test never passes) and writes zeros for
# the text of a .pchtxt string patch, whose record also had a fixed size that a long line
# overran. Eden fixed these after this pin; the same fixes are made here. Its .pchtxt reader also
# takes every line as a record or a flag: the credits at the end of a real patch file then wrote
# over the start of the game's code. Only records and known flags are read here
# (headless/mods_check.cpp checks all of it).
# This IPS/pchtxt parser is a complete, audited Encore source; CMake only
# selects it and must never mutate its functions during configuration.
set(EDEN_MAINTAINED_IPS_LAYER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/file_sys/ips_layer.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_IPS_LAYER}")
    message(FATAL_ERROR "Missing maintained native IPS layer")
endif()
# The patch manager: a missing mod root must never enter its sorting and dereference loops, and an
# .ips patch is named after the build ID in either case.
# Native patch manager: select a complete Encore-maintained source, never mutate upstream C++ here.
set(EDEN_MAINTAINED_PATCH_MANAGER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/file_sys/patch_manager.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_PATCH_MANAGER}")
    message(FATAL_ERROR "Missing maintained native patch manager")
endif()
get_target_property(core_sources core SOURCES)
list(REMOVE_ITEM core_sources file_sys/ips_layer.cpp file_sys/patch_manager.cpp)
list(APPEND core_sources "${EDEN_MAINTAINED_IPS_LAYER}" "${EDEN_MAINTAINED_PATCH_MANAGER}")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")

# The rate of the vsync clock a game runs on (60 Hz, or what an FPS patch asks for: 120, 240) is
# published for the renderer: frames a display has no refresh for are not presented
# (headless/display_refresh.h).
# Encore's native VSync/compose correction is a complete maintained unit.
set(EDEN_MAINTAINED_VI_CONDUCTOR
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/vi/conductor.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_VI_CONDUCTOR}")
    message(FATAL_ERROR "Missing maintained VI conductor")
endif()
target_include_directories(core PRIVATE "${EDEN_PORT_DIR}")
get_target_property(core_sources core SOURCES)
list(REMOVE_ITEM core_sources hle/service/vi/conductor.cpp)
list(APPEND core_sources "${EDEN_MAINTAINED_VI_CONDUCTOR}")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")

# Nvdrv sessions borrow process memory until their final handles are unmapped.
# Retain the process across that interval, including service shutdown ordering.
set(EDEN_MAINTAINED_NVDRV_CONTAINER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/nvdrv/core/container.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_NVDRV_CONTAINER}")
    message(FATAL_ERROR "Missing maintained nvdrv session container")
endif()
get_target_property(core_sources core SOURCES)
list(REMOVE_ITEM core_sources hle/service/nvdrv/core/container.cpp)
list(APPEND core_sources "${EDEN_MAINTAINED_NVDRV_CONTAINER}")
set_property(TARGET core PROPERTY SOURCES "${core_sources}")
# Finalize alone leaves both event references and its owner process open.
# Use the same paired close as the other HID event owners.
# Maintained full-source HID event lifetime correction; immutable upstream preserved.
set(EDEN_HID_RESOURCE "${PORT_ROOT}/vendor/encore-active/eden-core/src/hid_core/resource_manager.cpp")
if(NOT EXISTS "${EDEN_HID_RESOURCE}")
    message(FATAL_ERROR "Missing maintained HID resource manager")
endif()
get_target_property(hid_sources hid_core SOURCES)
list(FIND hid_sources resource_manager.cpp hid_resource_original)
if(hid_resource_original EQUAL -1)
    message(FATAL_ERROR "Pinned HID resource source moved; requalify")
endif()
list(REMOVE_ITEM hid_sources resource_manager.cpp)
list(APPEND hid_sources "${EDEN_HID_RESOURCE}")
set_property(TARGET hid_core PROPERTY SOURCES "${hid_sources}")


# R435 DEV Fullkey LIFO witness is maintained as complete C++ in encore-active.
# hid_core selects one variant in the NPad source selector below.

# Clang 18 trips over libstdc++ range constraints for implicit vector-to-span
# conversions inside these generic lambdas. Use the equivalent pointer/count
# constructor for every variable-argument wrapper.
# Native nvdrv span conversion has one maintained, complete header.
# Keep the existing staged include priority, but never rewrite the header in CMake.
set(ioctl_header "core/hle/service/nvdrv/devices/ioctl_serialization.h")
set(EDEN_MAINTAINED_IOCTL
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/${ioctl_header}")
if(NOT EXISTS "${EDEN_MAINTAINED_IOCTL}")
    message(FATAL_ERROR "Missing maintained nvdrv ioctl serialization header")
endif()
file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/core/hle/service/nvdrv/devices")
configure_file("${EDEN_MAINTAINED_IOCTL}"
    "${PORT_BUILD_DIR}/include/${ioctl_header}" COPYONLY)
target_include_directories(core BEFORE PRIVATE "${PORT_BUILD_DIR}/include")

# Cached build trees may still hold the old generated slab header even after
# its CMake rewrite was removed. A stale include would hide the maintained
# mutex and object destructor. Purge only the derived build-tree copy.
file(REMOVE "${PORT_BUILD_DIR}/include/core/hle/kernel/k_slab_heap.h")

# Thread finalization helpers are complete tracked headers in encore-active.
# native-hle-overrides.cmake stages those headers without text replacements.

# Game exit: the application's page table frees every physical page it maps (~1 s for a 4 GiB
# game) although the kernel shutdown that finalizes it recreates the memory manager at the next
# initialization. Skip those frees during a kernel shutdown; an in-game process exit (applets)
# still frees its pages.
file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/k_page_table_base.cpp" page_table_source)
set(page_free_old [=[        // Get physical pages.
        KPageGroup pg(m_system.Kernel(), m_block_info_manager);
        this->MakePageGroup(pg, addr, size / PageSize);

        // Free the pages.
        pg.CloseAndReset(m_system.Kernel());
    };]=])
string(FIND "${page_table_source}" "${page_free_old}" page_free_at)
if(page_free_at LESS 0)
    message(FATAL_ERROR "Pinned page table finalization changed")
endif()
string(REPLACE "${page_free_old}" [=[        // The memory manager is recreated after a kernel shutdown.
        if (m_system.Kernel().IsShuttingDown()) {
            return;
        }

        // Get physical pages.
        KPageGroup pg(m_system.Kernel(), m_block_info_manager);
        this->MakePageGroup(pg, addr, size / PageSize);

        // Free the pages.
        pg.CloseAndReset(m_system.Kernel());
    };]=] page_table_source "${page_table_source}")
write_derived("${PORT_BUILD_DIR}/k_page_table_base.cpp" "${page_table_source}")
get_target_property(page_table_core_sources core SOURCES)
list(REMOVE_ITEM page_table_core_sources hle/kernel/k_page_table_base.cpp)
list(APPEND page_table_core_sources "${PORT_BUILD_DIR}/k_page_table_base.cpp")
set_property(TARGET core PROPERTY SOURCES "${page_table_core_sources}")

# A server's stopped flag only covers its inner request loop; stopping the CPU
# immediately after it fires can abandon the applet destructor mid-cleanup.
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
set(server_header "core/hle/service/server_manager.h")
file(READ "${PROJECT_SOURCE_DIR}/src/${server_header}" server_header_source)
string(REPLACE "    Result LoopProcess();" "    void RequestStop();\n    Result LoopProcess();" server_header_source "${server_header_source}")
if(EDEN_DEV_PROFILE)
    string(REPLACE "    Mutex m_selection_mutex;" "    Mutex m_selection_mutex;\n    std::string m_eden_names;" server_header_source "${server_header_source}")
endif()
write_derived("${PORT_BUILD_DIR}/include/${server_header}" "${server_header_source}")
file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/service/server_manager.cpp" server_source)
string(REPLACE "ServerManager::~ServerManager() {\n    // Signal stop.\n    m_stop_source.request_stop();\n    m_wakeup_event->Signal(m_system.Kernel());"
    "void ServerManager::RequestStop() {\n    m_stop_source.request_stop();\n    m_wakeup_event->Signal(m_system.Kernel());\n}\n\nServerManager::~ServerManager() {\n    RequestStop();" server_source "${server_source}")
if(EDEN_DEV_PROFILE)
    # Development: split a slow manager destruction into its phases.
    string(PREPEND server_source "#include <chrono>\n#include <cstdio>\n")
    function(eden_patch_server match replacement)
        string(FIND "${server_source}" "${match}" found_at)
        if(found_at LESS 0)
            message(FATAL_ERROR "Pinned ServerManager destructor changed")
        endif()
        string(REPLACE "${match}" "${replacement}" patched "${server_source}")
        set(server_source "${patched}" PARENT_SCOPE)
    endfunction()
    eden_patch_server([=[    // Add the new server to sm: and get the moved server port.
    Kernel::KServerPort* server_port{};]=] [=[    // Add the new server to sm: and get the moved server port.
    Kernel::KServerPort* server_port{};
    m_eden_names += service_name + " ";]=])
    eden_patch_server([=[    // Create a new port.
    auto* port = Kernel::KPort::Create(m_system.Kernel());]=] [=[    // Create a new port.
    auto* port = Kernel::KPort::Create(m_system.Kernel());
    m_eden_names += service_name + " ";]=])
    eden_patch_server([=[ServerManager::~ServerManager() {
    RequestStop();]=] [=[ServerManager::~ServerManager() {
    RequestStop();
    const auto eden_t0 = std::chrono::steady_clock::now();]=])
    eden_patch_server([=[    m_stopped.Wait();
    m_threads.clear();]=] [=[    m_stopped.Wait();
    const auto eden_t1 = std::chrono::steady_clock::now();
    m_threads.clear();
    const auto eden_t2 = std::chrono::steady_clock::now();]=])
    eden_patch_server([=[    // Clean up sessions.]=] [=[    const auto eden_t3 = std::chrono::steady_clock::now();
    size_t eden_sessions = 0;
    // Clean up sessions.]=])
    eden_patch_server([=[        delete session;
    }

    // Close wakeup event.]=] [=[        delete session;
        ++eden_sessions;
    }
    const auto eden_t4 = std::chrono::steady_clock::now();

    // Close wakeup event.]=])
    eden_patch_server([=[        // Write event is owned by ServiceManager
    }
}]=] [=[        // Write event is owned by ServiceManager
    }
    const auto eden_t5 = std::chrono::steady_clock::now();
    const auto eden_span = [](auto a, auto b) { return std::chrono::duration<double, std::milli>(b - a).count(); };
    if (eden_span(eden_t0, eden_t5) >= 10.0) {
        std::fprintf(stderr, "EDEN_SHUTDOWN_DTOR manager=%p services=%s stopped=%.1f threads=%.1f ports=%.1f sessions=%.1f n=%zu events=%.1f\n",
                     static_cast<void*>(this), m_eden_names.c_str(), eden_span(eden_t0, eden_t1), eden_span(eden_t1, eden_t2),
                     eden_span(eden_t2, eden_t3), eden_span(eden_t3, eden_t4), eden_sessions, eden_span(eden_t4, eden_t5));
    }
}]=])
endif()
write_derived("${PORT_BUILD_DIR}/server_manager.cpp" "${server_source}")
get_target_property(core_sources core SOURCES)
list(REMOVE_ITEM core_sources hle/service/server_manager.cpp)
list(APPEND core_sources "${PORT_BUILD_DIR}/server_manager.cpp")
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

# Replace SDL audio with the optional native sink; the renderer stays null.
get_target_property(audio_sources audio_core SOURCES)
list(FILTER audio_sources EXCLUDE REGEX "sink/sdl3_sink\\.")
set_property(TARGET audio_core PROPERTY SOURCES "${audio_sources}")
get_target_property(audio_definitions audio_core COMPILE_DEFINITIONS)
list(REMOVE_ITEM audio_definitions HAVE_SDL3)
set_property(TARGET audio_core PROPERTY COMPILE_DEFINITIONS "${audio_definitions}")
get_target_property(audio_libraries audio_core LINK_LIBRARIES)
list(REMOVE_ITEM audio_libraries SDL3::SDL3)
set_property(TARGET audio_core PROPERTY LINK_LIBRARIES "${audio_libraries}")
get_target_property(audio_interface audio_core INTERFACE_LINK_LIBRARIES)
list(REMOVE_ITEM audio_interface SDL3::SDL3 "$<LINK_ONLY:SDL3::SDL3>")
set_property(TARGET audio_core PROPERTY INTERFACE_LINK_LIBRARIES "${audio_interface}")

# Reuse the independently authored native ABI contracts from the research.
set(pad_contract "${PORT_ROOT}/third_party")
set(audio_contract "${PORT_ROOT}/third_party")
file(SHA256 "${pad_contract}/ps5_pad.hpp" pad_hash)
file(SHA256 "${audio_contract}/native_audio.hpp" audio_hash)
if(NOT pad_hash STREQUAL "6a9708fe7ab59afa69899e1981e84decf1492a97e8ebd08194f8e27841a00ee0" OR
   NOT audio_hash STREQUAL "5274633c4f7cd4598fc4cdbfe5b044cbfca908845eb22157e73a80dca8faa0f6")
    message(FATAL_ERROR "Native device contracts changed; review the adapter ABI first.")
endif()
# Guest rumble: with no mapped buttons (this frontend binds the virtual_gamepad engine), send each
# player's left and right vibration to the PS5 controller engine (headless/pad.cpp).
# Rumble fallback is a tracked, versioned C++ source rather than a
# configure-time copy with substitutions. Preserve the hid_core source list.
set(EDEN_MAINTAINED_RUMBLE_CONTROLLER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/hid_core/frontend/emulated_controller.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_RUMBLE_CONTROLLER}")
    message(FATAL_ERROR "Missing maintained native rumble controller")
endif()
get_target_property(controller_sources hid_core SOURCES)
list(FILTER controller_sources EXCLUDE REGEX "(^|/)emulated_controller\\.cpp$")
list(APPEND controller_sources "${EDEN_MAINTAINED_RUMBLE_CONTROLLER}")
set_property(TARGET hid_core PROPERTY SOURCES "${controller_sources}")
# A controller update reaches every applet resource that is assigned. One that is assigned but not
# activated yet has no controllers set up (NPad::Activate fills them in), and upstream calls
# through its null device. Buttons rarely changed in that window; the motion sensors change with
# every sample, so a game that registers a second applet resource crashed a few seconds after it
# started (seen on the console: page fault in NPad::ControllerUpdate from the pad thread).
# The active shipping NPad implementation plus the two original native
# null-pointer guards are maintained directly; no CMake source mutation.
set(EDEN_MAINTAINED_NPAD
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/hid_core/resources/npad/npad.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_NPAD}")
    message(FATAL_ERROR "Missing maintained native NPad controller")
endif()
# Only one NPad implementation is compiled. The DEV instrumentation includes
# the same two null guards as the normal maintained unit.
if(PS5_NATIVE AND EDEN_DEV_PROFILE)
    set(EDEN_MAINTAINED_NPAD_DEV
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/hid_core/resources/npad/npad_pause_diag.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_NPAD_DEV}")
        message(FATAL_ERROR "Missing maintained diagnostic NPad source")
    endif()
    set(EDEN_NPAD_SELECTED "${EDEN_MAINTAINED_NPAD_DEV}")
else()
    set(EDEN_NPAD_SELECTED "${EDEN_MAINTAINED_NPAD}")
endif()
get_target_property(npad_sources hid_core SOURCES)
list(FILTER npad_sources EXCLUDE REGEX "(^|/)npad\\.cpp$")
list(APPEND npad_sources "${EDEN_NPAD_SELECTED}")
set_property(TARGET hid_core PROPERTY SOURCES "${npad_sources}")
add_library(eden-pad STATIC "${EDEN_PORT_DIR}/pad.cpp"
    "${PROJECT_SOURCE_DIR}/src/input_common/input_engine.cpp"
    "${PROJECT_SOURCE_DIR}/src/input_common/input_poller.cpp"
    "${PROJECT_SOURCE_DIR}/src/input_common/drivers/virtual_gamepad.cpp")
target_include_directories(eden-pad PUBLIC "${EDEN_PORT_DIR}" "${pad_contract}" "${audio_contract}" "${PROJECT_SOURCE_DIR}/src")
target_link_libraries(eden-pad PUBLIC common)
target_compile_options(eden-pad PRIVATE -fno-rtti $<$<BOOL:${PS5_NATIVE}>:-femulated-tls>)
target_sources(audio_core PRIVATE "${EDEN_PORT_DIR}/audio.cpp")
target_include_directories(audio_core PRIVATE "${EDEN_PORT_DIR}" "${pad_contract}" "${audio_contract}")
# The native audio sink's exact pinned-source transform is maintained as C++.
set(EDEN_MAINTAINED_SINK_DETAILS
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/audio_core/sink/sink_details.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_SINK_DETAILS}")
    message(FATAL_ERROR "Missing maintained native audio sink")
endif()
# Keep native PCM queue/upmix/held-frame behavior in a tracked C++ source.
set(EDEN_MAINTAINED_SINK_STREAM
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/audio_core/sink/sink_stream.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_SINK_STREAM}")
    message(FATAL_ERROR "Missing maintained native audio stream")
endif()
# A bitfield expression yields 0/1, so explicitly restore the SRC flag's bit position.
# Preserve the source bitfield-position fix without regenerating this TU.
set(EDEN_MAINTAINED_VOICE_INFO
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/audio_core/renderer/voice/voice_info.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_VOICE_INFO}")
    message(FATAL_ERROR "Missing maintained voice source")
endif()
get_target_property(audio_sources audio_core SOURCES)
list(REMOVE_ITEM audio_sources sink/sink_details.cpp sink/sink_stream.cpp renderer/voice/voice_info.cpp)
list(APPEND audio_sources "${EDEN_MAINTAINED_SINK_DETAILS}" "${EDEN_MAINTAINED_SINK_STREAM}" "${EDEN_MAINTAINED_VOICE_INFO}")
set_property(TARGET audio_core PROPERTY SOURCES "${audio_sources}")
if(PS5_NATIVE)
    target_link_libraries(eden-pad PUBLIC "${sdk}/target/lib/libScePad.so" "${sdk}/target/lib/libSceUserService.so")
    target_link_libraries(audio_core PUBLIC "${sdk}/target/lib/libSceAudioOut.so")
else()
    add_library(eden-device-mock STATIC "${EDEN_PORT_DIR}/mock_devices.cpp")
    target_include_directories(eden-device-mock PUBLIC "${EDEN_PORT_DIR}" "${pad_contract}" "${audio_contract}")
    target_include_directories(eden-device-mock PRIVATE "${PROJECT_SOURCE_DIR}/src")
    target_link_libraries(eden-device-mock PRIVATE common)
    target_link_libraries(audio_core PUBLIC eden-device-mock)
endif()

# The Vulkan factory is byte-identical to the pinned source; only the
# OpenGL-only build requires a distinct maintained unit without Vulkan symbols.
set(EDEN_MAINTAINED_GL_VIDEO_FACTORY
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/video_core_opengl.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_GL_VIDEO_FACTORY}")
    message(FATAL_ERROR "Missing maintained OpenGL-only video core factory")
endif()
get_target_property(video_sources video_core SOURCES)
# A guest span must be rejected BEFORE IsContinuousRange walks GPU page tables.
# An out-of-space or wrapping address would otherwise index the page vectors.
# Preserve the normal range walk and all GPU cache operations for valid spans.
if(PS5_NATIVE)
    # One maintained native source: address-span and granular-page bounds.
    # No C++ replacement string or helper module is evaluated at configure.
    set(EDEN_NATIVE_GPU_MEMORY_MANAGER
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/memory_manager.cpp")
    if(NOT EXISTS "${EDEN_NATIVE_GPU_MEMORY_MANAGER}")
        message(FATAL_ERROR "Missing Encore-maintained GPU memory manager")
    endif()
    list(REMOVE_ITEM video_sources "memory_manager.cpp")
    list(APPEND video_sources "${EDEN_NATIVE_GPU_MEMORY_MANAGER}")
endif()
# R411: Eden #4473/#4477 are already applied once by the audited
# version-locked shipping backports to PROJECT_SOURCE_DIR before CMake.
if(PS5_NATIVE)
    foreach(gpu4473_item
        "buffer_cache/buffer_cache.h|gpu_modified_ranges.ForEachInRange(device_addr_out, range_size"
        "buffer_cache/buffer_cache.h|if (IsRegionGpuModified(device_addr, size))"
        "engines/kepler_compute.h|bool upload_dirty{};"
        "engines/kepler_compute.h|bool was_dirty;"
        "engines/kepler_compute.cpp|data.was_dirty || source_dirty"
        "dma_pusher.cpp|dma_state.method == ComputeInline && dma_state.non_incrementing")
        string(REPLACE "|" ";" gpu4473_pair "${gpu4473_item}")
        list(GET gpu4473_pair 0 gpu4473_path)
        list(GET gpu4473_pair 1 gpu4473_anchor)
        file(READ "${PROJECT_SOURCE_DIR}/src/video_core/${gpu4473_path}" gpu4473_source)
        string(FIND "${gpu4473_source}" "${gpu4473_anchor}" gpu4473_at)
        if(gpu4473_at LESS 0)
            message(FATAL_ERROR "Prepared Eden source lacks #4473/#4477: ${gpu4473_path}: ${gpu4473_anchor}")
        endif()
    endforeach()
endif()
if(NOT EDEN_PS5_VULKAN)
    list(FILTER video_sources EXCLUDE REGEX "^(renderer_vulkan|vulkan_common)/")
else()
    include("${EDEN_PORT_DIR}/vulkan.cmake")
endif()
list(REMOVE_ITEM video_sources video_core.cpp gpu.cpp)
if(EDEN_PS5_VULKAN)
    list(APPEND video_sources video_core.cpp)
else()
    list(APPEND video_sources "${EDEN_MAINTAINED_GL_VIDEO_FACTORY}")
endif()
# Remove a derived header left by the isolated classic-uniform experiment.
file(REMOVE "${PORT_BUILD_DIR}/include/video_core/buffer_cache/buffer_cache_base.h")
# Join the worker before its renderer/context and scheduler are destroyed.
# C++ members are destroyed in reverse declaration order.
file(READ "${PROJECT_SOURCE_DIR}/src/video_core/gpu.cpp" gpu_source)
string(REPLACE ": gpu_thread{system_}\n        , system{system_}" ": system{system_}" gpu_source "${gpu_source}")
string(REPLACE ", is_async{is_async_}" ", is_async{is_async_}\n        , gpu_thread{system_}" gpu_source "${gpu_source}")
string(REPLACE "    // Destruction of thread must be done before all (non trivial)\n    // previous members has been destroyed\n    VideoCommon::GPUThread::ThreadManager gpu_thread;\n" "" gpu_source "${gpu_source}")
string(REPLACE "    u64 pending_composite_fence{};" "    u64 pending_composite_fence{};\n    VideoCommon::GPUThread::ThreadManager gpu_thread;" gpu_source "${gpu_source}")
if(EDEN_PS5_OPENGL)
    set(EDEN_MAINTAINED_GL_BUFFER_CACHE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_buffer_cache.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_GL_BUFFER_CACHE}")
        message(FATAL_ERROR "Missing maintained OpenGL buffer cache source")
    endif()
    list(REMOVE_ITEM video_sources renderer_opengl/gl_buffer_cache.cpp)
    list(APPEND video_sources "${EDEN_MAINTAINED_GL_BUFFER_CACHE}")
    if(PS5_NATIVE)
        # PS5 permits reading an ended query while another query is active.
        # Retain the upstream NVIDIA workaround on all other builds.
        set(EDEN_MAINTAINED_GL_QUERY_CACHE
            "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_query_cache.cpp")
        if(NOT EXISTS "${EDEN_MAINTAINED_GL_QUERY_CACHE}")
            message(FATAL_ERROR "Missing maintained native OpenGL query cache")
        endif()
        list(REMOVE_ITEM video_sources renderer_opengl/gl_query_cache.cpp)
        list(APPEND video_sources "${EDEN_MAINTAINED_GL_QUERY_CACHE}")
    endif()
        # Guest draw instrumentation is selected from complete Encore sources.
    if(EDEN_DEV_PROFILE)
        # The development-only OpenGL copy diagnostics are a tracked C++
        # source, byte-for-byte equivalent to the old CMake substitution.
        set(EDEN_MAINTAINED_DEV_GL_TEXTURE
            "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_texture_cache.cpp")
        if(NOT EXISTS "${EDEN_MAINTAINED_DEV_GL_TEXTURE}")
            message(FATAL_ERROR "Missing maintained development GL texture cache")
        endif()
        list(REMOVE_ITEM video_sources renderer_opengl/gl_texture_cache.cpp)
        list(APPEND video_sources "${EDEN_MAINTAINED_DEV_GL_TEXTURE}")
        target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")
    endif()
    # Each profile selects one full translation unit; never splice C++ in CMake.
    set(EDEN_MAINTAINED_GL_RASTERIZER_ROOT
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl")
    set(EDEN_MAINTAINED_GL_RASTERIZER
        "${EDEN_MAINTAINED_GL_RASTERIZER_ROOT}/gl_rasterizer.cpp")
    if(EDEN_DEV_PROFILE)
        set(EDEN_MAINTAINED_GL_RASTERIZER
            "${EDEN_MAINTAINED_GL_RASTERIZER_ROOT}/gl_rasterizer_dev.cpp")
    endif()
    if(NOT EXISTS "${EDEN_MAINTAINED_GL_RASTERIZER}")
        message(FATAL_ERROR "Missing maintained OpenGL rasterizer variant")
    endif()
    list(REMOVE_ITEM video_sources renderer_opengl/gl_rasterizer.cpp)
    list(APPEND video_sources "${EDEN_MAINTAINED_GL_RASTERIZER}")
    # renderer_opengl.cpp is byte-identical to the pinned source. Keep the
    # original in video_sources: copying it into a derived TU adds no behavior.
    # Join the GPU worker before transferring its context to the teardown thread.
    if(PS5_NATIVE)
        # Native MacroJIT exception recovery is selected from Encore, not generated.
        set(EDEN_MAINTAINED_MACRO
            "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/macro.cpp")
        if(NOT EXISTS "${EDEN_MAINTAINED_MACRO}")
            message(FATAL_ERROR "Missing maintained native macro unit")
        endif()
        list(REMOVE_ITEM video_sources macro.cpp)
        list(APPEND video_sources "${EDEN_MAINTAINED_MACRO}")
    endif()
    # R345: PS5 compiles our versioned, complete GPU worker and queue sources.
    # No source-code string rewrites execute during native configuration.
    if(PS5_NATIVE)
        set(EDEN_ACTIVE_GPU "${PORT_ROOT}/vendor/encore-active/eden-gpu")
        if(EDEN_DEV_PROFILE)
            set(EDEN_GPU_WORKER_VARIANT "gpu_thread_dev.cpp")
        else()
            set(EDEN_GPU_WORKER_VARIANT "gpu_thread_quiet.cpp")
        endif()
        file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/common" "${PORT_BUILD_DIR}/include/video_core")
        configure_file("${EDEN_ACTIVE_GPU}/include/common/bounded_threadsafe_queue.h"
            "${PORT_BUILD_DIR}/include/common/bounded_threadsafe_queue.h" COPYONLY)
        configure_file("${EDEN_ACTIVE_GPU}/include/video_core/gpu_thread.h"
            "${PORT_BUILD_DIR}/include/video_core/gpu_thread.h" COPYONLY)
        configure_file("${EDEN_ACTIVE_GPU}/${EDEN_GPU_WORKER_VARIANT}"
            "${PORT_BUILD_DIR}/gpu_thread.cpp" COPYONLY)
        list(REMOVE_ITEM video_sources gpu_thread.cpp)
        list(APPEND video_sources "${PORT_BUILD_DIR}/gpu_thread.cpp")
        string(PREPEND gpu_source "#include <glad/glad.h>\n")
    else()
    # PS5 GPU queue is already copied from the complete eden-gpu source above.
    # Host-specific GPU header is a tracked source, not generated C++.
    set(EDEN_MAINTAINED_HOST_GPU_HEADER
        "${PORT_ROOT}/vendor/encore-active/eden-core/host-gpu/include/video_core/gpu_thread.h")
    if(NOT EXISTS "${EDEN_MAINTAINED_HOST_GPU_HEADER}")
        message(FATAL_ERROR "Missing maintained host GPU header")
    endif()
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/video_core")
    configure_file("${EDEN_MAINTAINED_HOST_GPU_HEADER}"
        "${PORT_BUILD_DIR}/include/video_core/gpu_thread.h" COPYONLY)
    endif()
    target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/include")
    string(REPLACE "    ~Impl() = default;" "    ~Impl() { gpu_thread.Stop(); if (renderer && Settings::IsOpenGL()) { renderer->Context().MakeCurrent(); glFinish(); } }" gpu_source "${gpu_source}")
    # Join before unique_ptr destruction clears GPU::impl: queued draws call back
    # through GPU::TickWork. NotifyShutdown also protects service-owned state.
    set(old_gpu_shutdown "    void NotifyShutdown() {\n        std::unique_lock lk{sync_mutex};\n        shutting_down.store(true, std::memory_order::relaxed);\n        sync_cv.notify_all();\n    }")
    string(FIND "${gpu_source}" "${old_gpu_shutdown}" gpu_shutdown_offset)
    if(gpu_shutdown_offset LESS 0)
        message(FATAL_ERROR "Pinned GPU shutdown changed")
    endif()
    string(REPLACE "${old_gpu_shutdown}"
        "    void NotifyShutdown() {\n        {\n            std::unique_lock lk{sync_mutex};\n            shutting_down.store(true, std::memory_order::relaxed);\n            sync_cv.notify_all();\n        }\n        gpu_thread.Stop();\n    }" gpu_source "${gpu_source}")
    # In-flight guest waits must also unwind before Stop can join the worker.
    foreach(unit dma_pusher engines/puller)
        # Prepared Eden source already has #4473/#4477; apply only native
        # shutdown-aware sync and profiling adaptations below.
        file(READ "${PROJECT_SOURCE_DIR}/src/video_core/${unit}.cpp" command_source)
        string(REPLACE "        sync_cv.wait(lk, [this]() { return synced; });"
            "        while (!synced && !system.IsShuttingDown())\n            sync_cv.wait_for(lk, std::chrono::milliseconds(10));\n        if (system.IsShuttingDown()) return false;" command_source "${command_source}")
        if(unit STREQUAL "dma_pusher" AND EDEN_DEV_PROFILE)
            # R405: time the genuine GPU fence wait, preserving the existing
            # bounded shutdown-aware CV loop and all guest synchronization.
            set(dma_fence_wait "        while (!synced && !system.IsShuttingDown())\n            sync_cv.wait_for(lk, std::chrono::milliseconds(10));")
            string(FIND "${command_source}" "${dma_fence_wait}" fence_at)
            if(fence_at LESS 0)
                message(FATAL_ERROR "Pinned guest GPU DMA fence wait changed")
            endif()
            string(REPLACE "${dma_fence_wait}"
                "        { ::Eden::Performance::DiagnosticActiveTimer dma_fence_timer(\n            ::Eden::Performance::gpu_dma_sync_wait, ::Eden::Performance::gpu_dma_sync_active_since_ns,\n            !synced && !system.IsShuttingDown());\n${dma_fence_wait}\n        }"
                command_source "${command_source}")
            string(PREPEND command_source "#include \"${EDEN_PORT_DIR}/performance.h\"\n")
        endif()
        string(REPLACE "    while (word != value) {" "    while (word != value && !dma_pusher.system.IsShuttingDown()) {" command_source "${command_source}")
        if(unit STREQUAL "engines/puller" AND EDEN_DEV_PROFILE)
            # R406: an unmatched guest semaphore can keep the GPU worker in
            # ReleaseFences() indefinitely. Observe entry/exit ONCE, never
            # poll clocks, write counters or change wait semantics per loop.
            set(puller_semaphore_loop "    while (word != value && !dma_pusher.system.IsShuttingDown()) {")
            string(FIND "${command_source}" "${puller_semaphore_loop}" puller_sem_at)
            if(puller_sem_at LESS 0)
                message(FATAL_ERROR "Pinned guest GPU puller semaphore acquire changed")
            endif()
            string(REPLACE "${puller_semaphore_loop}"
                "    ::Eden::Performance::DiagnosticActiveTimer semaphore_timer(\n        ::Eden::Performance::gpu_puller_semaphore_wait,\n        ::Eden::Performance::gpu_puller_semaphore_active_since_ns,\n        word != value && !dma_pusher.system.IsShuttingDown());\n${puller_semaphore_loop}"
                command_source "${command_source}")
            string(PREPEND command_source "#include \"${EDEN_PORT_DIR}/performance.h\"\n")
        endif()
        string(PREPEND command_source "#include <chrono>\n")
        string(REPLACE "/" "_" unit_name "${unit}")
        write_derived("${PORT_BUILD_DIR}/${unit_name}.cpp" "${command_source}")
        list(REMOVE_ITEM video_sources "${unit}.cpp")
        list(APPEND video_sources "${PORT_BUILD_DIR}/${unit_name}.cpp")
    endforeach()
    # Once the worker has joined, queued callbacks can never execute. Drop them
    # before waking waiters: some callbacks borrow their callers' stack storage.
    string(REPLACE "        gpu_thread.Stop();\n    }"
        "        gpu_thread.Stop();\n        {\n            std::lock_guard lock{sync_request_mutex};\n            sync_requests.clear();\n            sync_requests_stopped = true;\n        }\n        sync_request_cv.notify_all();\n    }" gpu_source "${gpu_source}")
    string(REPLACE "    u64 pending_composite_fence{};" "    bool sync_requests_stopped{}; // Protected by sync_request_mutex.\n    u64 pending_composite_fence{};" gpu_source "${gpu_source}")
    string(REPLACE "        const u64 fence = ++last_sync_fence;" "        if (sync_requests_stopped) return CurrentSyncRequestFence();\n        const u64 fence = ++last_sync_fence;" gpu_source "${gpu_source}")
    string(REPLACE "return CurrentSyncRequestFence() >= fence;" "return sync_requests_stopped || CurrentSyncRequestFence() >= fence;" gpu_source "${gpu_source}")
    # Queued CPU read flushes must own the download area's address range.
    # If a worker failure makes WaitForSyncOperation throw, OnCPURead's
    # stack unwinds while the callback can remain queued. Capturing the
    # local raster_area by reference would leave a dangling reference.
    set(gpu_read_capture_original "RequestSyncOperation([this, &raster_area]() {")
    string(FIND "${gpu_source}" "${gpu_read_capture_original}" gpu_read_capture_at)
    if(gpu_read_capture_at LESS 0)
        message(FATAL_ERROR "Pinned GPU read callback lifetime changed")
    endif()
    string(REPLACE "${gpu_read_capture_original}"
        "RequestSyncOperation([this, raster_area]() {"
        gpu_source "${gpu_source}")
    # A worker exception can stop GPU ticks before a pending CPU fence is
    # acknowledged. The ordinary shutdown cancellation runs only after
    # joining that worker, and cannot rescue a guest already stuck on its
    # CPU-side WaitForSyncOperation. Source-gated native correction: observe
    # the existing fatal GPU error without consuming it for other waiters.
    set(gpu_sync_wait_original [=[    void WaitForSyncOperation(const u64 fence) {
        std::unique_lock lck{sync_request_mutex};
        sync_request_cv.wait(lck, [this, fence] { return sync_requests_stopped || CurrentSyncRequestFence() >= fence; });
    }]=])
    string(FIND "${gpu_source}" "${gpu_sync_wait_original}" gpu_sync_wait_position)
    if(gpu_sync_wait_position LESS 0)
        message(FATAL_ERROR "Pinned native GPU synchronization wait changed")
    endif()
    file(READ "${PORT_ROOT}/vendor/encore-active/eden-core/gpu-injections/gpu_sync_failure_wait.inc" gpu_sync_wait_replacement)
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${PORT_ROOT}/vendor/encore-active/eden-core/gpu-injections/gpu_sync_failure_wait.inc")
    string(REPLACE "${gpu_sync_wait_original}" "${gpu_sync_wait_replacement}"
        gpu_source "${gpu_source}")
    string(PREPEND gpu_source "#include \"${EDEN_PORT_DIR}/gpu_failure.h\"\n")
    # TickWork previously unlocked its mutex through the raw object while a
    # unique_lock still believed it owned that mutex. On an exception from a
    # GPU callback, the unique_lock destructor would attempt another unlock.
    # Keep ownership tracking correct before worker failure propagation.
    # A continuously replenished sync request queue must not monopolize the
    # worker's GPUTick command: replay only the FIFO batch already queued
    # when the tick began. New requests retain their own queued GPU ticks.
    # Advance each fence ONLY after its callback returns normally.
    set(gpu_tick_lock_original [=[        while (!sync_requests.empty()) {
            auto request = std::move(sync_requests.front());
            sync_requests.pop_front();
            sync_request_mutex.unlock();
            request();
            current_sync_fence.fetch_add(1, std::memory_order_release);
            sync_request_mutex.lock();
            sync_request_cv.notify_all();
        }]=])
    set(gpu_tick_lock_safe [=[        for (auto remaining = sync_requests.size(); remaining != 0; --remaining) {
            auto request = std::move(sync_requests.front());
            sync_requests.pop_front();
            lck.unlock();
            request();
            current_sync_fence.fetch_add(1, std::memory_order_release);
            lck.lock();
            sync_request_cv.notify_all();
        }]=])
    string(FIND "${gpu_source}" "${gpu_tick_lock_original}" gpu_tick_lock_position)
    if(gpu_tick_lock_position LESS 0)
        message(FATAL_ERROR "Pinned native GPU callback lock ownership changed")
    endif()
    string(REPLACE "${gpu_tick_lock_original}" "${gpu_tick_lock_safe}"
        gpu_source "${gpu_source}")
    # Commit a GPU sync fence only after its callback enters the FIFO.
    # On a throwing copy/allocation, no unfulfillable fence may be issued.
    set(gpu_enqueue_fence_original [=[        const u64 fence = ++last_sync_fence;
        sync_requests.emplace_back(std::forward<Func>(action));
        return fence;]=])
    set(gpu_enqueue_fence_atomic [=[        sync_requests.emplace_back(std::forward<Func>(action));
        return ++last_sync_fence;]=])
    string(FIND "${gpu_source}" "${gpu_enqueue_fence_original}" gpu_enqueue_fence_position)
    if(gpu_enqueue_fence_position LESS 0)
        message(FATAL_ERROR "Pinned native GPU sync enqueue/fence contract changed")
    endif()
    string(REPLACE "${gpu_enqueue_fence_original}" "${gpu_enqueue_fence_atomic}"
        gpu_source "${gpu_source}")
    string(REPLACE "GPU::~GPU() = default;" "GPU::~GPU() { impl->NotifyShutdown(); }" gpu_source "${gpu_source}")
    string(REPLACE "void GPU::PushGPUEntries(s32 channel, Tegra::CommandList&& entries) {"
        "void GPU::PushGPUEntries(s32 channel, Tegra::CommandList&& entries) {\n    static std::atomic<unsigned> submissions{};\n    const auto count = ++submissions;\n    if (count <= 3) LOG_INFO(Render_OpenGL, \"EDEN_GUEST_GPU_SUBMIT count={} channel={}\", count, channel);"
        gpu_source "${gpu_source}")
    if(EDEN_DEV_PROFILE)
        string(PREPEND gpu_source "#include \"${EDEN_PORT_DIR}/performance.h\"\n")
        string(REPLACE "    if (count <= 3) LOG_INFO(Render_OpenGL, \"EDEN_GUEST_GPU_SUBMIT count={} channel={}\", count, channel);"
            "    if (count <= 3 || ::Eden::Performance::BootTrace()) LOG_INFO(Render_OpenGL, \"EDEN_GUEST_GPU_SUBMIT count={} channel={} entries={}\", count, channel, entries.command_lists.size());"
            gpu_source "${gpu_source}")
    endif()
endif()
write_derived("${PORT_BUILD_DIR}/gpu.cpp" "${gpu_source}")
list(APPEND video_sources "${PORT_BUILD_DIR}/gpu.cpp")
if(EDEN_DEV_PROFILE)
    # Complete Encore-maintained conditional-render diagnostic; do not
    # generate a source by injecting text into the pinned Maxwell engine.
    set(EDEN_MAINTAINED_DEV_MAXWELL
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/engines/maxwell_3d.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_DEV_MAXWELL}")
        message(FATAL_ERROR "Missing maintained Maxwell diagnostic source")
    endif()
    target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")
    list(REMOVE_ITEM video_sources engines/maxwell_3d.cpp)
    list(APPEND video_sources "${EDEN_MAINTAINED_DEV_MAXWELL}")
endif()
# Upstream ProsperoEden 673f675 (#72), adapted to pinned Eden 5f142c79:
# salvage complete shader pipeline entries after a damaged tail.
# Shader cache tail recovery is maintained directly in Encore C++.
# CMake selects the source; the adjacent .inc is a tracked, sole-owner header.
set(EDEN_MAINTAINED_SHADER_ENVIRONMENT
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/shader_environment.cpp")
set(EDEN_MAINTAINED_SHADER_READER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/shader_cache_reader.inc")
if(NOT EXISTS "${EDEN_MAINTAINED_SHADER_ENVIRONMENT}" OR
   NOT EXISTS "${EDEN_MAINTAINED_SHADER_READER}")
    message(FATAL_ERROR "Missing maintained shader cache recovery source")
endif()
# R428: port upstream d7f2764 ASTC per-layer scratch without modifying
# the immutable Eden source package. Keep the converted pixel order and BC
# output offsets; only the temporary decode batch width changes.
# The one-layer ASTC scratch optimization is a complete Encore source.
# Keep the original pinned package immutable; CMake only selects this TU.
set(EDEN_MAINTAINED_TEXTURE_UTIL
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/texture_cache/util.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_TEXTURE_UTIL}")
    message(FATAL_ERROR "Missing maintained ASTC texture utility")
endif()
list(REMOVE_ITEM video_sources texture_cache/util.cpp)
list(APPEND video_sources "${EDEN_MAINTAINED_TEXTURE_UTIL}")
list(REMOVE_ITEM video_sources shader_environment.cpp)
list(APPEND video_sources "${EDEN_MAINTAINED_SHADER_ENVIRONMENT}")
# Eden #4473/#4477 are already applied once to the pinned source by
# tools/apply-eden-backports.sh and validated there; never shadow headers twice.
set_property(TARGET video_core PROPERTY SOURCES "${video_sources}")

if(PS5_NATIVE)
    target_compile_definitions(libzstd_static PRIVATE ZSTD_TRACE=0)
    # The native title cannot chdir. Set the shared path manager's data root
    # directly so every core/log/cache path remains inside its writable mount.
    # The native data/config/cache roots are a tracked C++ override.
    set(EDEN_MAINTAINED_NATIVE_PATHS
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/fs/path_util.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_PATHS}")
        message(FATAL_ERROR "Missing maintained native filesystem path source")
    endif()
    get_target_property(common_sources common SOURCES)
    # Compile the native common thread-name diagnostic from maintained C++.
    set(EDEN_MAINTAINED_NATIVE_THREAD
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/thread.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_THREAD}")
        message(FATAL_ERROR "Missing maintained common thread source")
    endif()
    list(REMOVE_ITEM common_sources thread.cpp)
    list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_THREAD}")
    # PS5 advertises invariant TSC but no CPUID leaf0x15. The original fallback
    # was inside that leaf's branch, leaving frequency zero on this hardware.
    # Native invariant TSC fallback is maintained C++, not configure-time surgery.
    set(EDEN_MAINTAINED_NATIVE_CPU_FEATURES
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/cpu_features.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_CPU_FEATURES}")
        message(FATAL_ERROR "Missing maintained native CPU frequency source")
    endif()
    list(REMOVE_ITEM common_sources cpu_features.cpp)
    list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_CPU_FEATURES}")
    # Native directory enumeration retains the prior helper verbatim.
    set(EDEN_MAINTAINED_NATIVE_FS
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/fs/fs.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_FS}")
        message(FATAL_ERROR "Missing maintained common filesystem source")
    endif()
    list(REMOVE_ITEM common_sources fs/fs.cpp)
    list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_FS}")
    list(REMOVE_ITEM common_sources fs/path_util.cpp)
    list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_PATHS}")
    target_include_directories(common PRIVATE "${EDEN_PORT_DIR}")
    set_property(TARGET common PROPERTY SOURCES "${common_sources}")
    # Prefer this build's matching decoder headers over the C dependency
    # bundle's older FFmpeg headers exposed through OpenSSL's include root.
    target_include_directories(video_core BEFORE PRIVATE "${FFmpeg_INCLUDE_DIR}")
    # The older SDK omits DCCP's IP protocol name (wire value 33, also used by
    # Service::Sockets::Protocol). socket() still decides runtime support.
    get_target_property(core_sources core SOURCES)
    # Observe permitted *guest* DNS/traffic at its own HLE IPC/socket boundary,
    # after the cached R295 domain filter patch is applied to pinned Eden.
    # No packets are edited, no host resolver setting is changed, and these
    # wrappers are completely silent when Detailed Logging is disabled.
    # The audited resolver is owned by Encore; no C++ substitutions in CMake.
    set(EDEN_MAINTAINED_GUEST_DNS
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/sockets/sfdnsres.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_GUEST_DNS}")
        message(FATAL_ERROR "Missing maintained guest DNS resolver")
    endif()
    list(REMOVE_ITEM core_sources hle/service/sockets/sfdnsres.cpp)
    list(APPEND core_sources "${EDEN_MAINTAINED_GUEST_DNS}")

    # Guest socket audit instrumentation is a complete Encore-maintained source.
    # Preserve shipping BSD backports; do not rewrite C++ during configure.
    set(EDEN_MAINTAINED_GUEST_BSD
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/sockets/bsd.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_GUEST_BSD}")
        message(FATAL_ERROR "Missing maintained audited guest BSD source")
    endif()
    list(REMOVE_ITEM core_sources hle/service/sockets/bsd.cpp)
    list(APPEND core_sources "${EDEN_MAINTAINED_GUEST_BSD}")

    # Keep immutable firmware outside the small writable title-data quota.
    # Native BISFactory declaration is kept in a narrowly scoped include root.
    # Do not expose the whole encore-core/src tree as an include override.
    set(EDEN_MAINTAINED_BIS_INCLUDE_ROOT
        "${PORT_ROOT}/vendor/encore-active/eden-core/include")
    set(EDEN_MAINTAINED_BIS_HEADER
        "${EDEN_MAINTAINED_BIS_INCLUDE_ROOT}/core/file_sys/bis_factory.h")
    set(EDEN_MAINTAINED_BIS_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/file_sys/bis_factory.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_BIS_HEADER}" OR NOT EXISTS "${EDEN_MAINTAINED_BIS_SOURCE}")
        message(FATAL_ERROR "Missing maintained native BISFactory pair")
    endif()
    # Prevent an older configure's derived header shadowing the tracked ABI.
    file(REMOVE "${PORT_BUILD_DIR}/include/core/file_sys/bis_factory.h")
    target_include_directories(core BEFORE PUBLIC "${EDEN_MAINTAINED_BIS_INCLUDE_ROOT}")
    list(REMOVE_ITEM core_sources file_sys/bis_factory.cpp)
    list(APPEND core_sources "${EDEN_MAINTAINED_BIS_SOURCE}")
    # Use the tracked source for native firmware lookup.
    set(EDEN_MAINTAINED_NATIVE_FILESYSTEM
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/hle/service/filesystem/filesystem.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_FILESYSTEM}")
        message(FATAL_ERROR "Missing maintained native filesystem source")
    endif()
    list(REMOVE_ITEM core_sources hle/service/filesystem/filesystem.cpp)
    list(APPEND core_sources "${EDEN_MAINTAINED_NATIVE_FILESYSTEM}")
    # A single checked-in native socket-wakeup implementation; no CMake C++ rewrites.
    set(EDEN_NATIVE_NETWORK_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/internal_network/network.cpp")
    if(NOT EXISTS "${EDEN_NATIVE_NETWORK_SOURCE}")
        message(FATAL_ERROR "Missing maintained native network source")
    endif()
    list(REMOVE_ITEM core_sources internal_network/network.cpp)
    list(APPEND core_sources "${EDEN_NATIVE_NETWORK_SOURCE}")
    # Reuse the getifaddrs path instead of newer BSD route-format helpers.
    # Keep its existing zero-gateway fallback; PS5 route discovery is unqualified.
    list(REMOVE_ITEM core_sources internal_network/network_interface.cpp)
    # Native interface enumeration selects the maintained FreeBSD branch.
    set(EDEN_MAINTAINED_NATIVE_NET_INTERFACES
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/core/internal_network/network_interface.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_NET_INTERFACES}")
        message(FATAL_ERROR "Missing maintained native network interface source")
    endif()
    list(APPEND core_sources "${EDEN_MAINTAINED_NATIVE_NET_INTERFACES}")
    set_property(TARGET core PROPERTY SOURCES "${core_sources}")
    # Eden only uses Boost.Process v1's header-only async_pipe. Its unused v2
    # library assumes newer FreeBSD process APIs than the PS5 SDK supplies.
    foreach(property LINK_LIBRARIES INTERFACE_LINK_LIBRARIES)
        get_target_property(libraries core ${property})
        list(REMOVE_ITEM libraries Boost::process)
        set_property(TARGET core PROPERTY ${property} "${libraries}")
    endforeach()
    target_include_directories(core PRIVATE "$<TARGET_PROPERTY:boost_process,INTERFACE_INCLUDE_DIRECTORIES>")
    target_link_libraries(core PRIVATE "$<TARGET_PROPERTY:boost_process,INTERFACE_LINK_LIBRARIES>")
    set(native_template "${PORT_ROOT}/../ps5-native-app-boilerplate")
    # Compile one complete maintained allocator variant; never synthesize C here.
    option(EDEN_HEAP_ARENAS "Per-thread arenas inside the owned heap" ON)
    option(EDEN_HEAP_GUARD "Development trailing heap corruption guards" OFF)
    set(EDEN_ACTIVE_HEAP_DIR "${PORT_ROOT}/vendor/encore-active/eden-build/tooling/native")
    if(EDEN_HEAP_ARENAS)
        set(EDEN_HEAP_UNIT "app_heap_arenas.c")
    else()
        set(EDEN_HEAP_UNIT "app_heap_flat.c")
    endif()
    set(EDEN_HEAP_SOURCE "${EDEN_ACTIVE_HEAP_DIR}/${EDEN_HEAP_UNIT}")
    if(NOT EXISTS "${EDEN_HEAP_SOURCE}" OR NOT EXISTS "${EDEN_ACTIVE_HEAP_DIR}/heap_guard.h")
        message(FATAL_ERROR "Missing maintained Encore heap source or guard header")
    endif()
    set(eden_app_crt "${native_template}/tooling/native/app_crt.cpp")
    if(EDEN_PS5_VULKAN AND EDEN_VULKAN_DRIVER STREQUAL "RADV")
        # The native RADV startup is a complete, reviewed boilerplate override.
        # CMake selects it directly; no inline source rewriting.
        set(EDEN_MAINTAINED_RADV_CRT
            "${PORT_ROOT}/vendor/encore-active/eden-build/tooling/native/app_crt_radv.cpp")
        if(NOT EXISTS "${EDEN_MAINTAINED_RADV_CRT}")
            message(FATAL_ERROR "Missing maintained native RADV CRT")
        endif()
        set(eden_app_crt "${EDEN_MAINTAINED_RADV_CRT}")
    endif()
    add_executable(eden-headless "${EDEN_PORT_DIR}/main.cpp" "${PORT_ROOT}/src/aligned_alloc.c"
        "${EDEN_PORT_DIR}/heap_pages.cpp" "${EDEN_PORT_DIR}/performance.cpp"
        "${EDEN_PORT_DIR}/crash_report.cpp" "${EDEN_PORT_DIR}/stop_limit.cpp"
        "${EDEN_PORT_DIR}/elevation/elevation.cpp" "${EDEN_PORT_DIR}/ps5_net_compat.c"
        "${EDEN_PORT_DIR}/network_domain_rules.c"
        "${EDEN_PORT_DIR}/network_audit.c"
        "${EDEN_PORT_DIR}/network_audit_sockets.c"
        "${eden_app_crt}" "${PORT_ROOT}/src/lifecycle.c"
        "${EDEN_HEAP_SOURCE}")
    # Guest DNS IPC and native launcher both call eden_network_host_blocked(),
    # supplied once by eden-headless's native network_domain_rules.c.
    # The guest derived DNS source includes the matching policy prototype.
    target_include_directories(core PRIVATE "${EDEN_PORT_DIR}")
    target_compile_definitions(eden-headless PRIVATE PS5_NATIVE=1)
    if(EDEN_HEAP_GUARD)
        set_property(SOURCE "${EDEN_HEAP_SOURCE}" TARGET_DIRECTORY eden-headless
            APPEND PROPERTY COMPILE_DEFINITIONS EDEN_HEAP_GUARD=1)
    endif()
    # Only main.cpp needs to recompile when the SHA changes. The stable
    # video_core and other native app objects keep their incremental caches.
    if(NOT DEFINED EDEN_ENCORE_SOURCE_COMMIT)
        set(EDEN_ENCORE_SOURCE_COMMIT "unknown")
    endif()
    if(NOT EDEN_ENCORE_SOURCE_COMMIT STREQUAL "unknown")
        string(LENGTH "${EDEN_ENCORE_SOURCE_COMMIT}" encore_commit_len)
        if(NOT encore_commit_len EQUAL 40 OR
           NOT EDEN_ENCORE_SOURCE_COMMIT MATCHES "^[0-9a-f]+$")
            message(FATAL_ERROR "EDEN_ENCORE_SOURCE_COMMIT must be a 40-char lowercase Git SHA")
        endif()
    endif()
    set_property(SOURCE "${EDEN_PORT_DIR}/main.cpp" APPEND PROPERTY
        COMPILE_DEFINITIONS "EDEN_NATIVE_SOURCE_COMMIT=\"${EDEN_ENCORE_SOURCE_COMMIT}\"")
    if(EDEN_SPARSE_JIT_DEV)
        target_compile_definitions(eden-headless PRIVATE EDEN_SPARSE_JIT_DEV=1)
    endif()
    # Native-title libc rejects socket fcntl and its resolver may depend on an
    # unloaded WebKit module. ps5_net_compat.c supplies sceNetResolver DNS and
    # translates only refused socket flags to native SO_NBIO.
    target_link_options(eden-headless PRIVATE -Wl,--wrap=fcntl
        -Wl,--wrap=connect -Wl,--wrap=send -Wl,--wrap=sendto
        -Wl,--wrap=recv -Wl,--wrap=recvfrom)
    set_property(TARGET eden-headless APPEND PROPERTY LINK_DEPENDS
        "${PORT_ROOT}/tools/link-headless-native.sh" "${PORT_ROOT}/tools/unwind.ld"
        "${PORT_ROOT}/tools/app-symbols.map")
    if(EDEN_PS5_VULKAN AND EDEN_VULKAN_DRIVER STREQUAL "RADV")
        set_property(TARGET eden-headless APPEND PROPERTY LINK_DEPENDS
            "${PORT_ROOT}/tools/radv-link-eden.sh"
            "${PORT_ROOT}/../mihawk-vulkan-review/tools/radv-link.sh")
    endif()
    target_compile_definitions(common PRIVATE PS5_NATIVE=1 YUZU_BUNDLED_OPENSSL=1)
else()
    add_executable(eden-headless "${EDEN_PORT_DIR}/main.cpp" "${PORT_ROOT}/src/aligned_alloc.c")
    target_link_options(eden-headless PRIVATE -Wl,--wrap=aligned_alloc)
    add_executable(eden-romfs-check "${EDEN_PORT_DIR}/romfs_check.cpp")
    target_include_directories(eden-romfs-check PRIVATE "${PROJECT_SOURCE_DIR}/src")
    target_link_libraries(eden-romfs-check PRIVATE core)
    target_compile_options(eden-romfs-check PRIVATE -fno-rtti)
    add_executable(eden-scalar-check "${EDEN_PORT_DIR}/scalar_check.cpp")
    target_include_directories(eden-scalar-check PRIVATE "${PROJECT_SOURCE_DIR}/src")
    target_link_libraries(eden-scalar-check PRIVATE dynarmic)
    add_executable(eden-memory-check "${EDEN_PORT_DIR}/memory_check.cpp")
    target_include_directories(eden-memory-check PRIVATE "${PROJECT_SOURCE_DIR}/src")
    target_link_libraries(eden-memory-check PRIVATE dynarmic common)
    target_compile_definitions(eden-memory-check PRIVATE EDEN_SHARED_JIT_AVAILABLE=$<BOOL:${EDEN_SHARED_JIT}>)
    target_compile_options(eden-scalar-check PRIVATE -fno-rtti)
    add_executable(eden-ryujinx-check "${EDEN_PORT_DIR}/ryujinx_check.cpp")
    # Run on the host: whole shader cache entries survive a damaged tail.
    add_executable(eden-shader-cache-check "${EDEN_PORT_DIR}/shader_cache_check.cpp")
    target_include_directories(eden-shader-cache-check PRIVATE "${PROJECT_SOURCE_DIR}/src")
    target_link_libraries(eden-shader-cache-check PRIVATE video_core)
    target_compile_options(eden-shader-cache-check PRIVATE -fno-rtti)
    add_executable(eden-mods-check "${EDEN_PORT_DIR}/mods_check.cpp")
    target_include_directories(eden-mods-check PRIVATE "${PROJECT_SOURCE_DIR}/src")
    target_link_libraries(eden-mods-check PRIVATE core)
    target_compile_options(eden-mods-check PRIVATE -fno-rtti)
    # The settings store's check is written with assert(): they stay in a release build.
    add_executable(eden-settings-check "${EDEN_PORT_DIR}/preferences_check.cpp")
    target_link_libraries(eden-settings-check PRIVATE core)
    target_compile_options(eden-settings-check PRIVATE -UNDEBUG)
    add_executable(eden-devices-check "${EDEN_PORT_DIR}/devices_check.cpp")
    target_link_libraries(eden-devices-check PRIVATE core eden-pad eden-device-mock)
    target_compile_options(eden-devices-check PRIVATE -fno-rtti)
endif()
target_include_directories(eden-headless PRIVATE "${PROJECT_SOURCE_DIR}/src")
# The R-label is injected by the native compiler, independently of sce_sys.
set(EDEN_LAUNCHER_BUILD_LABEL "R1" CACHE STRING "Eden Encore compiled R revision")
if(NOT EDEN_LAUNCHER_BUILD_LABEL MATCHES "^R[0-9]+$")
    message(FATAL_ERROR "Invalid Eden launcher revision: ${EDEN_LAUNCHER_BUILD_LABEL}")
endif()
target_compile_definitions(eden-headless PRIVATE
    EDEN_LAUNCHER_BUILD_LABEL=\"${EDEN_LAUNCHER_BUILD_LABEL}\"
    EDEN_SHARED_JIT_AVAILABLE=$<BOOL:${EDEN_SHARED_JIT}>
    EDEN_JIT_COMPILE_BATCH_AVAILABLE=$<BOOL:${EDEN_JIT_COMPILE_BATCH}>)
target_link_libraries(eden-headless PRIVATE core eden-pad)
add_library(eden-metadata STATIC "${EDEN_PORT_DIR}/metadata_bridge.cpp")
target_include_directories(eden-metadata PUBLIC "${EDEN_PORT_DIR}" PRIVATE "${PROJECT_SOURCE_DIR}/src")
target_link_libraries(eden-metadata PUBLIC core stb)
target_compile_options(eden-metadata PRIVATE -fno-rtti -Wall -Wextra -Werror -Wno-unused-parameter)
if(PS5_NATIVE)
    target_compile_options(eden-metadata PRIVATE -femulated-tls)
endif()
add_dependencies(eden-headless eden-metadata)

option(EDEN_HOST_ASAN "Instrument host emulator code for memory diagnostics" OFF)
if(EDEN_HOST_ASAN)
    if(PS5_NATIVE)
        message(FATAL_ERROR "EDEN_HOST_ASAN is a Linux host diagnostic only")
    endif()
    # Generated guest instructions and custom fiber stacks are not covered.
    foreach(asan_target common core audio_core video_core hid_core eden-pad eden-device-mock eden-headless)
        target_compile_options(${asan_target} PRIVATE -fsanitize=address -g1 -fno-omit-frame-pointer
            -fno-sanitize-address-use-after-scope -fsanitize-address-use-after-return=never)
    endforeach()
    target_link_options(eden-headless PRIVATE -fsanitize=address)
endif()
target_compile_options(eden-headless PRIVATE -Wall -Wextra -Werror -Wno-unused-parameter -fwrapv $<$<COMPILE_LANGUAGE:CXX>:-fno-rtti>)
if(PS5_NATIVE)
    target_compile_options(eden-headless PRIVATE -femulated-tls)
    option(EDEN_DEVICE_FRONTEND "Enable the unqualified native controller/audio frontend" OFF)
    target_compile_definitions(eden-headless PRIVATE EDEN_DEVICE_FRONTEND=$<BOOL:${EDEN_DEVICE_FRONTEND}>)
endif()

# Consume the frozen, relocatable 4.6 SDK as one complete profile.
option(EDEN_PS5_OPENGL "Use the PS5 EGL/OpenGL frontend" OFF)
set(EDEN_DEV_ROM_ID "" CACHE STRING "Development-only first-launch title ID; empty uses launcher")
if(NOT EDEN_DEV_ROM_ID STREQUAL "")
    string(LENGTH "${EDEN_DEV_ROM_ID}" dev_id_length)
    if(NOT dev_id_length EQUAL 16 OR NOT EDEN_DEV_ROM_ID MATCHES "^[0-9A-Fa-f]+$")
        message(FATAL_ERROR "Development title ID must be 16 hex digits")
    endif()
    target_compile_definitions(eden-headless PRIVATE EDEN_DEV_ROM_ID="${EDEN_DEV_ROM_ID}")
endif()
option(EDEN_DEV_PROFILE "Development-only autoboot, timed input replay and profiling" OFF)
set(EDEN_DEV_PROFILE_TITLE "" CACHE STRING "Title ID the development profile boots and replays input for")
option(EDEN_DEV_WAIT_CALLERS "Development-only bounded GPU-owner caller sampling" OFF)
if(EDEN_DEV_WAIT_CALLERS)
    if(NOT EDEN_DEV_PROFILE OR NOT PS5_NATIVE)
        message(FATAL_ERROR "Caller sampling requires the native development profile")
    endif()
    target_compile_definitions(eden-headless PRIVATE EDEN_DEV_WAIT_CALLERS=1)
endif()
if(EDEN_DEV_PROFILE)
    string(LENGTH "${EDEN_DEV_PROFILE_TITLE}" profile_title_length)
    if(NOT profile_title_length EQUAL 16 OR NOT EDEN_DEV_PROFILE_TITLE MATCHES "^[0-9A-Fa-f]+$")
        message(FATAL_ERROR "EDEN_DEV_PROFILE needs EDEN_DEV_PROFILE_TITLE (a 16-digit title ID)")
    endif()
    target_compile_definitions(eden-headless PRIVATE EDEN_DEV_PROFILE=1
        EDEN_DEV_PROFILE_TITLE="${EDEN_DEV_PROFILE_TITLE}")
endif()
option(EDEN_GPU_PROBE "Run bounded graphics-only architecture matrix, then exit" OFF)
if(EDEN_GPU_PROBE)
    if(NOT EDEN_PS5_OPENGL)
        message(FATAL_ERROR "GPU probe requires native OpenGL")
    endif()
    target_compile_definitions(eden-headless PRIVATE EDEN_GPU_PROBE=1)
endif()
if(EDEN_PS5_OPENGL)
    if(NOT PS5_NATIVE OR NOT ENABLE_OPENGL)
        message(FATAL_ERROR "PS5 graphics requires the native OpenGL build")
    endif()
    # Audited PS5 OpenGL source snapshot. It includes SDK 1.0.1 plus the reviewed post-release
    # constant-buffer/alignment and scanout-flush fixes; tools/build-opengl-sdk.sh verifies its
    # source commit and installed manifest before CMake sees it.
    set(gl46 "${PORT_ROOT}/.local/ps5-opengl-sdk-ad2807d")
    set(gl46_commit "ad2807d41cef2681882a9ee0d20808779f74b7cd")
    if(NOT EXISTS "${gl46}/lib/libps5_opengl_core33.a" OR NOT EXISTS "${gl46}/manifest.sha256" OR
       NOT EXISTS "${gl46}/ENCORE_SOURCE_COMMIT")
        message(FATAL_ERROR "Missing audited PS5 OpenGL SDK in ${gl46}; run make prepare")
    endif()
    file(READ "${gl46}/ENCORE_SOURCE_COMMIT" gl46_built_commit)
    string(STRIP "${gl46_built_commit}" gl46_built_commit)
    if(NOT gl46_built_commit STREQUAL gl46_commit)
        message(FATAL_ERROR "Frozen OpenGL source commit changed: ${gl46_built_commit}")
    endif()
    file(SHA256 "${gl46}/manifest.sha256" gl46_manifest_hash)
    if(EDEN_DEV_PROFILE)
        target_compile_definitions(eden-headless PRIVATE EDEN_DEV_GL_VERSION="${gl46_commit}-${gl46_manifest_hash}")
    endif()
    set(PS5OpenGL_DIR "${gl46}/lib/cmake/PS5OpenGL" CACHE PATH "Frozen Eden graphics SDK" FORCE)
    find_package(PS5OpenGL CONFIG REQUIRED PATHS "${gl46}/lib/cmake/PS5OpenGL" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    target_sources(eden-headless PRIVATE "${EDEN_PORT_DIR}/graphics.cpp")
    # The loading screen's shader as a string for the OpenGL window; the Vulkan HUD pass includes
    # the same two files (vulkan_hud.frag).
    file(READ "${EDEN_PORT_DIR}/loading_wordmark.glsl" loading_wordmark)
    file(READ "${EDEN_PORT_DIR}/loading_scene.glsl" loading_scene)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
        "${EDEN_PORT_DIR}/loading_wordmark.glsl" "${EDEN_PORT_DIR}/loading_scene.glsl")
    write_derived("${PORT_BUILD_DIR}/include/loading_scene_glsl.h"
        "// Generated from loading_wordmark.glsl and loading_scene.glsl.\n#pragma once\ninline constexpr const char* kLoadingSceneGlsl = R\"glsl(\n${loading_wordmark}${loading_scene})glsl\";\n")
    target_compile_definitions(eden-headless PRIVATE EDEN_PS5_OPENGL=1)
    target_link_libraries(eden-headless PRIVATE PS5OpenGL::OpenGL glad)
endif()
    # Launcher UI: its own small OpenGL renderer, mixer and screens (headless/prosperoeden/pe),
    # all gone before a game starts.
    if(PS5_NATIVE)
        set(launcher_dir "${EDEN_PORT_DIR}/prosperoeden")
        target_sources(eden-headless PRIVATE
            "${launcher_dir}/runtime_shims.cpp"
            "${launcher_dir}/radio_input.c")
        target_include_directories(eden-headless PRIVATE "${launcher_dir}" "${PORT_ROOT}/third_party")
        if(EDEN_PS5_OPENGL)
            set(launcher_sources
                "${launcher_dir}/frontend.cpp"
                "${launcher_dir}/eden_services.cpp"
                "${launcher_dir}/pe/audio/mixer.cpp"
                "${launcher_dir}/pe/audio/sounds.cpp"
                "${launcher_dir}/pe/audio/wav.cpp"
                "${launcher_dir}/pe/core/strings.cpp"
                "${launcher_dir}/pe/gfx/bidi.cpp"
                "${launcher_dir}/pe/gfx/draw_list.cpp"
                "${launcher_dir}/pe/gfx/font.cpp"
                "${launcher_dir}/pe/gfx/gl_batch.cpp"
                "${launcher_dir}/pe/gfx/gl_program.cpp"
                "${launcher_dir}/pe/gfx/harfbuzz.cpp"
                "${launcher_dir}/pe/gfx/image.cpp"
                "${launcher_dir}/pe/gfx/system_fonts.cpp"
                "${launcher_dir}/pe/platform/audio_out.cpp"
                "${launcher_dir}/pe/platform/display_egl.cpp"
                "${launcher_dir}/pe/ui/browse.cpp"
                "${launcher_dir}/pe/ui/home.cpp"
                "${launcher_dir}/pe/ui/launcher.cpp"
                "${launcher_dir}/pe/ui/library.cpp"
                "${launcher_dir}/pe/ui/mapping.cpp"
                "${launcher_dir}/pe/ui/settings.cpp"
                "${launcher_dir}/pe/ui/switch_theme.cpp"
                "${launcher_dir}/pe/ui/textures.cpp"
                "${launcher_dir}/pe/ui/widgets.cpp")
            target_sources(eden-headless PRIVATE ${launcher_sources})
            # The launcher calls OpenGL by name (the SDK's headers), not through glad.
            set(launcher_definitions "GL_GLEXT_PROTOTYPES=1")
            if(EXISTS "${EDEN_PORT_DIR}/ryujinx_saves.h")
                list(APPEND launcher_definitions "EDEN_SAVE_IMPORT=1")
            endif()
            set_source_files_properties(${launcher_sources}
                PROPERTIES COMPILE_DEFINITIONS "${launcher_definitions}")
            # Text in the scripts the baked font lacks: the console's own fonts, shaped by HarfBuzz
            # (a pinned source release, tools/deps.json) and drawn through stb_truetype.
            set(harfbuzz_dir "${PORT_ROOT}/.deps/harfbuzz-12.3.2/src")
            if(NOT EXISTS "${harfbuzz_dir}/harfbuzz.cc")
                message(FATAL_ERROR "HarfBuzz is missing (${harfbuzz_dir}): run make deps")
            endif()
            set_source_files_properties(
                "${launcher_dir}/pe/gfx/system_fonts.cpp" "${launcher_dir}/pe/gfx/harfbuzz.cpp"
                PROPERTIES INCLUDE_DIRECTORIES "${harfbuzz_dir};${PORT_ROOT}/tools/launcher/stb")
            # HarfBuzz is not ours to tidy: its warnings are off.
            set_source_files_properties("${launcher_dir}/pe/gfx/harfbuzz.cpp" PROPERTIES COMPILE_OPTIONS "-w")
        else()
            target_sources(eden-headless PRIVATE "${launcher_dir}/frontend_stub.cpp")
        endif()
        target_link_libraries(eden-headless PRIVATE eden-metadata)
    endif()

if(EDEN_PS5_VULKAN)
    # Both backends import the same system module; use the superset facade.
    get_target_property(gl_imports PS5OpenGL::OpenGL INTERFACE_LINK_LIBRARIES)
    list(FILTER gl_imports EXCLUDE REGEX "/libSceAgcDriver[.]so$")
    list(APPEND gl_imports "${PORT_ROOT}/build/stubs/libSceAgcDriver.so")
    set_property(TARGET PS5OpenGL::OpenGL PROPERTY INTERFACE_LINK_LIBRARIES "${gl_imports}")
    target_compile_definitions(eden-headless PRIVATE EDEN_PS5_VULKAN=1)
    if(EDEN_VULKAN_DRIVER STREQUAL "RADV")
        target_compile_definitions(eden-headless PRIVATE EDEN_PS5_RADV=1)
    endif()
    target_include_directories(eden-headless BEFORE PRIVATE "${PORT_BUILD_DIR}/include")
endif()

option(EDEN_DEV_VULKAN "Force Vulkan for a development autoboot without changing preferences" OFF)
if(EDEN_DEV_VULKAN)
    if(NOT EDEN_PS5_VULKAN OR EDEN_DEV_ROM_ID STREQUAL "")
        message(FATAL_ERROR "EDEN_DEV_VULKAN requires Vulkan and an explicit development ROM ID")
    endif()
    target_compile_definitions(eden-headless PRIVATE EDEN_DEV_VULKAN=1)
endif()

# Capture reproducible GPU compatibility evidence without changing any
# Maxwell/Fermi instructions or swallowing unsupported feature failures.
include("${CMAKE_CURRENT_LIST_DIR}/gpu_native_observability.cmake")
# Disabled native GPU coherency bridge, explicit developer compilation only.
include("${CMAKE_CURRENT_LIST_DIR}/guest_write_deferred_bridge.cmake")
