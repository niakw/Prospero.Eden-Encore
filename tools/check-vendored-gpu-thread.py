#!/usr/bin/env python3
"""Reproduce and verify the exact PS5 GPU worker, queue and header fork.

R345 isolates the old CMake source derivations and proves that shipping and
opt-in detailed diagnostic builds use the committed, portable equivalents.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'vendor/sources/eden'
TARGET = ROOT / 'vendor/encore-active/eden-gpu'
CMAKE_SOURCE = ROOT / 'headless/CMakeLists.txt'
START = '    # PS5-only stop-aware producer wait; the pinned upstream queue has a'
END = '    # R345_LEGACY_SOURCE_END'


def derive(profile: str, directory: Path) -> dict[str, bytes]:
    content = CMAKE_SOURCE.read_text()
    assert content.count(START) == content.count(END) == 1
    begin = content.index(START)
    end = content.index(END, begin)
    fragment = content[begin:end]
    assert 'EmplaceWaitWithStopToken' in fragment
    assert 'eden_gpu_queue_capacity 32' in fragment
    assert 'write_derived("${PORT_BUILD_DIR}/gpu_thread.cpp"' in fragment
    assert 'write_derived("${PORT_BUILD_DIR}/include/video_core/gpu_thread.h"' in fragment
    header = f'''cmake_minimum_required(VERSION 3.25)
set(PROJECT_SOURCE_DIR "{SOURCE.resolve().as_posix()}")
set(EDEN_PORT_DIR "{(ROOT / 'headless').resolve().as_posix()}")
set(PORT_BUILD_DIR "{directory.as_posix()}")
set(PS5_NATIVE ON)
set(EDEN_DEV_PROFILE {"ON" if profile == "dev" else "OFF"})
set(video_sources "gpu_thread.cpp")
function(write_derived PATH DATA)
  get_filename_component(DIR "${{PATH}}" DIRECTORY)
  file(MAKE_DIRECTORY "${{DIR}}")
  file(WRITE "${{PATH}}" "${{DATA}}")
endfunction()
'''
    script = directory.parent / f'gpu-gen-{profile}.cmake'
    script.write_text(header + fragment)
    subprocess.run(['cmake', '-P', str(script)], check=True, timeout=45, cwd=ROOT)
    absolute = (ROOT / 'headless').resolve().as_posix() + '/'
    found = {}
    for name in ('gpu_thread.cpp', 'include/video_core/gpu_thread.h',
                 'include/common/bounded_threadsafe_queue.h'):
        data = (directory / name).read_text()
        # The old build emitted absolute includes pointing to whichever Mac or
        # Linux directory configured it. Correct them to use headless's actual
        # CMake include path, making tracked translations portable.
        data = data.replace(absolute, '')
        assert '/private/tmp/eden-' not in data and '/home/runner/work/' not in data
        found[name] = data.encode()
    return found


def expected_files() -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix='eden-gpu-fork-') as d:
        temp = Path(d)
        quiet = derive('quiet', temp / 'quiet')
        dev = derive('dev', temp / 'dev')
        assert quiet['include/video_core/gpu_thread.h'] == dev['include/video_core/gpu_thread.h']
        assert quiet['include/common/bounded_threadsafe_queue.h'] == dev['include/common/bounded_threadsafe_queue.h']
        return {
            'gpu_thread_quiet.cpp': quiet['gpu_thread.cpp'],
            'gpu_thread_dev.cpp': dev['gpu_thread.cpp'],
            'include/video_core/gpu_thread.h': dev['include/video_core/gpu_thread.h'],
            'include/common/bounded_threadsafe_queue.h': dev['include/common/bounded_threadsafe_queue.h'],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--materialize', action='store_true')
    args = parser.parse_args()
    generated = expected_files()
    if args.materialize:
        for relative, content in generated.items():
            path = TARGET / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file() or path.read_bytes() != content:
                path.write_bytes(content)
    present = {str(p.relative_to(TARGET)): p for p in TARGET.rglob('*') if p.is_file()}
    assert present.keys() == generated.keys(), (generated.keys() - present.keys(), present.keys() - generated.keys())
    for relative, content in generated.items():
        assert present[relative].read_bytes() == content, f'R345 generated GPU source mismatch: {relative}'
    assert b'SPSCQueue<CommandDataContainer, 32>' in generated['include/video_core/gpu_thread.h']
    assert b'EmplaceWaitWithStopToken' in generated['include/common/bounded_threadsafe_queue.h']
    assert b'DiagnosticTimer' in generated['gpu_thread_dev.cpp']
    assert b'DiagnosticTimer' not in generated['gpu_thread_quiet.cpp']
    cmake = CMAKE_SOURCE.read_text()
    assert 'vendor/encore-active/eden-gpu' in cmake
    assert cmake.count('configure_file("${EDEN_ACTIVE_GPU}/') == 3
    assert 'EDEN_GPU_WORKER_VARIANT "gpu_thread_dev.cpp"' in cmake
    assert 'EDEN_GPU_WORKER_VARIANT "gpu_thread_quiet.cpp"' in cmake
    assert cmake.index('if(PS5_NATIVE)\n        set(EDEN_ACTIVE_GPU') < cmake.index('    # R345_LEGACY_SOURCE_END')
    # Execute the real PS5 CMake path in script mode, not merely a source-text
    # assertion: the resulting compiler inputs must match both committed
    # variants, and none may require the historical replacement pipeline.
    marker='    if(PS5_NATIVE)\n        set(EDEN_ACTIVE_GPU'
    after='    else()\n    # PS5-only stop-aware producer wait;'
    assert cmake.count(marker)==cmake.count(after)==1
    native=cmake[cmake.index(marker):cmake.index(after,cmake.index(marker))]+'    endif()\n'
    with tempfile.TemporaryDirectory(prefix='eden-gpu-cmake-contract-') as d:
        work=Path(d)
        for profile in ('dev','quiet'):
            build=work/profile
            build.mkdir()
            script=work/f'{profile}.cmake'
            script.write_text(f'cmake_minimum_required(VERSION 3.25)\n'
                              f'set(PORT_ROOT "{ROOT.as_posix()}")\n'
                              f'set(PORT_BUILD_DIR "{build.as_posix()}")\n'
                              f'set(PS5_NATIVE ON)\n'
                              f'set(EDEN_DEV_PROFILE {"ON" if profile=="dev" else "OFF"})\n'
                              f'set(video_sources "gpu_thread.cpp")\n'
                              f'set(gpu_source "original")\n'+native)
            subprocess.run(['cmake','-P',str(script)],cwd=ROOT,check=True,timeout=30)
            assert (build/'gpu_thread.cpp').read_bytes()==generated[f'gpu_thread_{profile}.cpp']
            for name in ('include/video_core/gpu_thread.h', 'include/common/bounded_threadsafe_queue.h'):
                assert (build/name).read_bytes()==generated[name], (profile,name)
    print('VENDORED_GPU_CMAKE_NATIVE_BRANCH_OK direct source copies for dev/quiet')
    print('VENDORED_GPU_THREAD_EQUIVALENT_OK', len(generated),
          'original 32-slot FIFO, stop-aware worker, dev/quiet source variants')


if __name__ == '__main__':
    main()
