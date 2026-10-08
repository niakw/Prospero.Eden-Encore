#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
patch=(root/'headless/backports/eden-sm-host-wait.patch').read_text()
for needle in (
    'Kernel::GetCurrentThread(kernel).IsDummyThread()',
    'std::this_thread::sleep_for(1ms)',
    'SessionRequestHandlerFactory factory',
    'std::scoped_lock',
    'IAudioController::GetSetSys()',
    'std::call_once(m_set_sys_once',
    'GetSetSys()->GetAudioOutputMode',
):
    assert needle in patch, needle
assert 'kernel.IsShuttingDown()' not in patch
assert 'GetCurrentEmuThread' not in patch
print('Host-thread-safe blocking services + lazy audio dependency PASS')
