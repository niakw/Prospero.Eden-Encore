#!/usr/bin/env python3
"""Require exact equivalence of the maintained HID resource source to its pinned base."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
original=(root/"vendor/sources/eden/src/hid_core/resource_manager.cpp").read_text()
maintained=(root/"vendor/encore-active/eden-core/src/hid_core/resource_manager.cpp").read_text()
old="input_event->Finalize(system.Kernel());"
new="service_context.CloseEvent(input_event);"
assert original.count(old)==1
assert maintained==original.replace(old,new)
assert maintained.count(new)==1
cmake=(root/"headless/CMakeLists.txt").read_text()
assert "set(EDEN_HID_RESOURCE " in cmake
assert 'list(FIND hid_sources resource_manager.cpp hid_resource_original)' in cmake
assert 'list(APPEND hid_sources "__DOLLAR__{EDEN_HID_RESOURCE}")'.replace("__DOLLAR__","$") in cmake
assert 'write_derived("__DOLLAR__{PORT_BUILD_DIR}/resource_manager.cpp"'.replace("__DOLLAR__","$") not in cmake
print("VENDORED_HID_RESOURCE_EQUIVALENT source=maintained")
