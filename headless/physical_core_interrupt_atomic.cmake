# SPDX-License-Identifier: GPL-3.0-or-later
# Correct the unsynchronized IsInterrupted read in the native derived source
# without changing the pinned vendor header's layout or source contents.
# Every read and write, including the optional profiling variant, must use
# atomic_ref; mixing plain and atomic accesses would itself be a data race.
# m_guard still orders the context pointers and coordinates Idle's CV.
if(NOT DEFINED physical_core_source)
    message(FATAL_ERROR "PhysicalCore atomic interrupt patch requires pinned source")
endif()
string(REGEX MATCHALL "m_is_interrupted" interrupt_accesses "${physical_core_source}")
list(LENGTH interrupt_accesses interrupt_access_count)
if(EDEN_DEV_PROFILE)
    set(expected_interrupt_access_count 6)
else()
    set(expected_interrupt_access_count 5)
endif()
if(NOT interrupt_access_count EQUAL expected_interrupt_access_count)
    message(FATAL_ERROR
        "PhysicalCore interrupt accesses changed: expected ${expected_interrupt_access_count}, found ${interrupt_access_count}")
endif()
# Checked source anchors. Keep the atomic load relaxed: no other state is
# published through this flag. m_guard remains the context/CV mutex.
foreach(anchor
    "if (m_is_interrupted)"
    "return m_is_interrupted;"
    "m_is_interrupted = true;"
    "m_is_interrupted = false;")
    string(FIND "${physical_core_source}" "${anchor}" interrupt_anchor_index)
    if(interrupt_anchor_index LESS 0)
        message(FATAL_ERROR "Pinned PhysicalCore interrupt source anchor changed: ${anchor}")
    endif()
endforeach()
if(EDEN_DEV_PROFILE)
    string(FIND "${physical_core_source}" "slept = !m_is_interrupted;" profile_interrupt_index)
    if(profile_interrupt_index LESS 0)
        message(FATAL_ERROR "Derived diagnostic interrupt read changed")
    endif()
endif()
set(interrupt_atomic_load
    "std::atomic_ref<const bool>{m_is_interrupted}.load(std::memory_order_relaxed)")
string(REPLACE "if (m_is_interrupted)"
    "if (${interrupt_atomic_load})" physical_core_source "${physical_core_source}")
string(REPLACE "return m_is_interrupted;"
    "return ${interrupt_atomic_load};" physical_core_source "${physical_core_source}")
string(REPLACE "m_is_interrupted = true;"
    "std::atomic_ref<bool>{m_is_interrupted}.store(true, std::memory_order_relaxed);"
    physical_core_source "${physical_core_source}")
string(REPLACE "m_is_interrupted = false;"
    "std::atomic_ref<bool>{m_is_interrupted}.store(false, std::memory_order_relaxed);"
    physical_core_source "${physical_core_source}")
if(EDEN_DEV_PROFILE)
    string(REPLACE "slept = !m_is_interrupted;"
        "slept = !${interrupt_atomic_load};" physical_core_source "${physical_core_source}")
endif()
# Derivation runs after the source-level profile/guest-fault overlays. The
# native compiler sees <atomic> via this generated source, no public ABI change.
string(PREPEND physical_core_source "#include <atomic>\n")
