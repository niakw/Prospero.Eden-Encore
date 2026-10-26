#!/usr/bin/env python3
"""R368: prove native Git SHA survives bash -> CMake -> C++ -> boot trace."""
from pathlib import Path
import os,shutil,subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
builder=(root/'tools/build-headless-native.sh').read_text()
cmake=(root/'headless/CMakeLists.txt').read_text()
main=(root/'headless/main.cpp').read_text()
performance=(root/'headless/performance.cpp').read_text()
workflow=(root/'.github/workflows/build-040-zbic.yml').read_text()
assert 'source_commit=$(git -C "$root" rev-parse --verify HEAD)' in builder
assert '[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]]' in builder
assert '-DEDEN_ENCORE_SOURCE_COMMIT="$source_commit"' in builder
assert 'bash tools/build-package.sh release-stage' in workflow
assert 'bash tools/build-package.sh dev' not in workflow
assert 'EDEN_TEST_ALL_ON' not in workflow
assert 'build/dev/PPSA99008' not in workflow
assert 'bash tools/build-headless-native.sh --graphics' in (
    root/'tools/build-package.sh').read_text()
assert 'EDEN_NATIVE_SOURCE_COMMIT' in cmake
assert cmake.count('set_property(SOURCE "${EDEN_PORT_DIR}/main.cpp" APPEND PROPERTY')==1
assert 'Eden::BootTrace::Line("source_sha=%s", EDEN_NATIVE_SOURCE_COMMIT);' in main
assert 'Eden::BootTrace::Line("source_sha=unknown");' in main
assert 'std::printf("EDEN_BUILD_SOURCE source_sha=%s\\n", EDEN_NATIVE_SOURCE_COMMIT);' in main
assert 'std::printf("EDEN_SESSION_SOURCE source_sha=%s\\n", EDEN_NATIVE_SOURCE_COMMIT);' in main
assert main.index('passed("session_start");') < main.index('std::printf("EDEN_SESSION_SOURCE')
assert 'if (Eden::NativeLogs::Detailed()) {' in main
assert 'std::printf("EDEN_TIME_ANCHOR epoch_ms=%lld mono_ns=%lld phase=session_start\\n",' in main
assert 'eden_network_audit_event("launcher", "session-start",' in main
assert main.index('passed("session_start");') < main.index('EDEN_TIME_ANCHOR')
assert main.index('EDEN_TIME_ANCHOR') < main.index('std::fflush(stdout);', main.index('EDEN_SESSION_SOURCE'))
assert 'clock_gettime(CLOCK_REALTIME, &real_clock)' in main
assert 'clock_gettime(CLOCK_MONOTONIC, &mono_clock)' in main
assert 'EDEN_TIME_ANCHOR epoch_ms=%lld mono_ns=%lld phase=frame_report frame=%u' in performance
assert 'ClockNs(CLOCK_REALTIME) / 1000000LL' in performance
assert 'ClockNs(CLOCK_MONOTONIC), frame' in performance
assert 'if (detailed_gpu_profile.load(std::memory_order_relaxed)) {' in performance

assert 'if (persist_detailed_logs)' in main
assert main.index('BootTrace::Begin(') < main.index('BootTrace::Line("source_sha=%s"')
assert 'Eden::BootTrace::Begin(Eden::kAppVersion, __DATE__ " " __TIME__);' in main
begin=cmake.index('    if(NOT DEFINED EDEN_ENCORE_SOURCE_COMMIT)')
# Read only the complete SHA validation stanza; no sparse/dense build switch
# terminates it because the PS5 now has one native JIT.
end=cmake.index('    # Native-title libc rejects socket fcntl',begin)
rules=cmake[begin:end]
assert 'EDEN_SPARSE_JIT_DEV' not in rules
assert 'message(FATAL_ERROR' in rules and 'EQUAL 40' in rules
compiler=shutil.which('cmake')
assert compiler,'cmake required'
with tempfile.TemporaryDirectory(prefix='eden-r368-sha-') as tmp:
    work=Path(tmp)
    (work/'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.22)\n'
        'project(eden_native_source_stamp LANGUAGES CXX)\n'
        'set(EDEN_PORT_DIR "${CMAKE_CURRENT_SOURCE_DIR}")\n'
        'add_executable(eden-headless main.cpp)\n' + rules)
    (work/'main.cpp').write_text(
        '#include <cstdio>\n'
        '#ifndef EDEN_NATIVE_SOURCE_COMMIT\n'
        '#error Native source commit macro missing\n'
        '#endif\n'
        'int main(){ std::puts(EDEN_NATIVE_SOURCE_COMMIT); }\n')
    env=os.environ.copy()
    if sys.platform=='darwin' and not env.get('SDKROOT'):
        sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
        if sdk.exists():env['SDKROOT']=str(sdk)
    sha='0f1e2d3c4b5a6978877665544332211000aabbcc'
    assert len(sha)==40
    for name,value in [('valid',sha),('fallback','unknown'),('bad','a'*39)]:
        folder=work/name
        p=subprocess.run([compiler,'-S',str(work),'-B',str(folder),
                          '-DEDEN_ENCORE_SOURCE_COMMIT='+value],
                         capture_output=True,text=True,env=env,timeout=25)
        if name=='bad':
            assert p.returncode != 0,(name,p.stdout,p.stderr)
            assert '40-char lowercase Git SHA' in p.stderr,(name,p.stderr)
            continue
        assert p.returncode == 0,(name,p.stdout,p.stderr)
        subprocess.run([compiler,'--build',str(folder)],check=True,
                       stdout=subprocess.DEVNULL,env=env,timeout=30)
        output=subprocess.check_output([str(folder/'eden-headless')],
                                       text=True,timeout=8).strip()
        assert output==value,(name,output,value)
print('PASS R368 native sha CMake/C++ provenance: valid, unknown, bad input guard')
