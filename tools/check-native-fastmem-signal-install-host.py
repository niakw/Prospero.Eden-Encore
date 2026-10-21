#!/usr/bin/env python3
"""Compile real source-extracted fastmem install/range guards with mock signal API."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
s=(root/"headless/fastmem_handler.cpp").read_text()
start="constexpr bool ValidCodeRange("
end="\nvoid Forward("
assert s.count(start)==s.count(end)==1
range_helper=start+s.split(start,1)[1].split(end,1)[0]
install="bool Install() {"+s.split("bool Install() {",1)[1].split("\n} // namespace",1)[0]
assert s.count("bool Install() {")==1
assert s.count("if (!impl || impl->range || !ValidCodeRange(impl->begin, impl->size) || !Install()) return;")==1
assert 'sigaction(SIGSEGV, &previous_segv, nullptr)' in install
assert install.index('sigaction(SIGSEGV, &previous_segv, nullptr)') > install.index('sigaction(SIGBUS, &action, &previous_bus)')
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler
fixture=r"""
#include <cassert>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <limits>
__RANGE__
static std::once_flag install_once;
static bool installed=false;
static struct sigaction previous_segv{}, previous_bus{};
static struct sigaction current_segv{},current_bus{};
static bool bus_failure=false;
static unsigned segv_installs=0,segv_restores=0,bus_installs=0;
void Handle(int, siginfo_t*, void*) {}
int MockSigaction(int which,const struct sigaction* requested,struct sigaction* previous) {
    assert(requested);
    if(which==SIGSEGV) {
        if(previous) {
            *previous=current_segv;
            ++segv_installs;
        } else {
            ++segv_restores;
        }
        current_segv=*requested;
        return 0;
    }
    assert(which==SIGBUS);
    ++bus_installs;
    if(bus_failure) return -1;
    if(previous) *previous=current_bus;
    current_bus=*requested;
    return 0;
}
#define sigaction(...) MockSigaction(__VA_ARGS__)
__INSTALL__
#undef sigaction
int main(int argc,char** argv) {
    assert(argc==2);
    assert(ValidCodeRange(1,1));
    assert(ValidCodeRange(100,200));
    assert(!ValidCodeRange(0,1));
    assert(!ValidCodeRange(~std::uint64_t{0},1));
    assert(!ValidCodeRange(1,0));
    assert(!ValidCodeRange(~std::uint64_t{0}-7,8));
    assert(ValidCodeRange(~std::uint64_t{0}-8,8));
    current_segv.sa_handler=SIG_IGN;
    current_bus.sa_handler=SIG_DFL;
    bus_failure=argv[1][0]=='f';
    const bool ok=Install();
    assert(ok==!bus_failure);
    assert(Install()==ok);
    assert(segv_installs==1 && bus_installs==1);
    if(bus_failure) {
        assert(segv_restores==1);
        assert(current_segv.sa_handler==SIG_IGN);
        assert(current_bus.sa_handler==SIG_DFL);
    } else {
        assert(segv_restores==0);
        assert(current_segv.sa_sigaction==Handle);
        assert(current_bus.sa_sigaction==Handle);
    }
}
""".replace("__RANGE__",range_helper).replace("__INSTALL__",install)
with tempfile.TemporaryDirectory(prefix="eden-fastmem-install-") as tmp:
    d=Path(tmp);cpp=d/"signal.cpp";exe=d/"signal"
    cpp.write_text(fixture)
    subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(cpp),"-o",str(exe)],check=True,timeout=90)
    for mode in ("failed_bus","success"):
        subprocess.run([str(exe),mode],check=True,timeout=20,capture_output=True)
print("FASTMEM_INSTALL_HOST_PASS both_or_neither=1 rollback=1 wrapped_ranges_rejected=1 sanitizer=1")
