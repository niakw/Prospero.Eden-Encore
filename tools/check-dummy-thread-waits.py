#!/usr/bin/env python3
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
patch=root/'headless/backports/eden-dummy-thread-waits.patch'
text=patch.read_text()
for needle in (
    'RequestDummyThreadWait(m_kernel)',
    'GetState() != ThreadState::Waiting || cur_thread->IsDummyThread()',
    'ClearWaitQueue()',
    'SetWaitResult(wait_result)',
    'SetState(kernel, ThreadState::Runnable)',
):
    assert needle in text, needle
cache=Path((root/'.local/headless-cache').read_text().strip())
src=cache/'source/src/core/hle/kernel'
with tempfile.TemporaryDirectory(prefix='encore-dummy-wait-') as tmp:
    tmp=Path(tmp)
    dst=tmp/'src/core/hle/kernel'; dst.mkdir(parents=True)
    for name in ('k_light_lock.cpp','k_thread.cpp'):
        shutil.copy2(src/name,dst/name)
    subprocess.run(['patch','--batch','--forward','-p1','-d',str(tmp)],
                   input=text,text=True,check=True,stdout=subprocess.DEVNULL)
    light=(dst/'k_light_lock.cpp').read_text()
    thread=(dst/'k_thread.cpp').read_text()
    assert 'cur_thread->RequestDummyThreadWait(m_kernel);' in light
    assert 'cur_thread->ClearWaitQueue();' in light
    assert 'if (m_wait_queue != nullptr)' in thread
    assert 'this->SetState(kernel, ThreadState::Runnable);' in thread
print('Dummy host-thread kernel wait backport applies to pinned Eden: PASS')
