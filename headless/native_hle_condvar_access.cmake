# SPDX-License-Identifier: GPL-3.0-or-later
# Native-only derived condition variable helpers. Unmapped guest memory may
# read as zero or ignore a write; successful helpers must validate the word.
if(NOT DEFINED eden_cv_source)
    message(FATAL_ERROR "Native condition variable guard requires derived source")
endif()
set(cv_read_old [=[    *out = GetCurrentMemory(kernel).Read32(GetInteger(address));
    return true;]=])
set(cv_read_new [=[    auto& memory = GetCurrentMemory(kernel);
    if (!memory.IsValidVirtualAddressRange(address, sizeof(u32))) {
        return false;
    }
    *out = memory.Read32(GetInteger(address));
    return true;]=])
set(cv_write_old [=[    GetCurrentMemory(kernel).Write32(GetInteger(address), val);
    return true;]=])
set(cv_write_new [=[    auto& memory = GetCurrentMemory(kernel);
    if (!memory.IsValidVirtualAddressRange(address, sizeof(u32))) {
        return false;
    }
    memory.Write32(GetInteger(address), val);
    return true;]=])
set(cv_atomic_old [=[    auto& monitor = GetCurrentProcess(kernel).GetExclusiveMonitor();]=])
set(cv_atomic_new [=[    if (!GetCurrentMemory(kernel).IsValidVirtualAddressRange(address, sizeof(u32))) {
        return false;
    }
    auto& monitor = GetCurrentProcess(kernel).GetExclusiveMonitor();]=])
set(cv_signal_old [=[        can_access = true;
        if (can_access) {
            UpdateLockAtomic(kernel, std::addressof(prev_tag), address, own_tag, Svc::HandleWaitMask);
        }]=])
set(cv_signal_new [=[        can_access = UpdateLockAtomic(kernel, std::addressof(prev_tag), address,
                                      own_tag, Svc::HandleWaitMask);]=])
foreach(pair IN ITEMS read write atomic signal)
    set(before "${cv_${pair}_old}")
    set(after "${cv_${pair}_new}")
    string(FIND "${eden_cv_source}" "${before}" at)
    if(at LESS 0)
        message(FATAL_ERROR "Pinned native condition variable ${pair} contract changed")
    endif()
    string(REPLACE "${before}" "" without "${eden_cv_source}")
    string(LENGTH "${eden_cv_source}" len_before)
    string(LENGTH "${without}" len_without)
    string(LENGTH "${before}" len_anchor)
    math(EXPR count "(${len_before} - ${len_without}) / ${len_anchor}")
    if(NOT count EQUAL 1)
        message(FATAL_ERROR "Native condition variable ${pair} contract not unique: ${count}")
    endif()
    string(REPLACE "${before}" "${after}" eden_cv_source "${eden_cv_source}")
endforeach()
