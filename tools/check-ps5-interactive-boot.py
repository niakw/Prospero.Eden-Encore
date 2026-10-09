#!/usr/bin/env python3
"""Regression: an all-on FC27 build opens the library on every fresh launch.

The previous dev build bypassed the library by default, including after the
player closed the title via the PS button. This tests the REAL constexpr boot
policy on the host and asserts integration with the actual PS5 launcher.
It does NOT run a PS5 application or game.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
main=(ROOT/"headless/main.cpp").read_text()
policy=(ROOT/"headless/dev_launch_policy.h").read_text()
assert '#include "dev_launch_policy.h"' in main
assert 'bool autoboot_pending = false;' in main
assert 'Eden::DevLaunch::BootIntent boot;' in main
assert 'boot.Observe(entry);' in main
assert 'boot.ShouldAutoboot(!last_crash.report.empty())' in main
assert 'EDEN_DEV_BOOT mode=%s' in main
assert 'if (std::exchange(autoboot_pending, false))' in main
assert 'selected_game = SelectProsperoEdenGame(launch_error);' in main
assert 'if (autoboot_pending && check_backend_recovery && !recovery_opengl && !launch_error.empty())' in main
assert 'autoboot_pending = true;' not in main
assert 'autoboot_pending ? "autoboot" : "launcher"' in main
assert 'if (token == "autoboot=on") requested = true;' in policy
assert 'if (token == "autoboot=off" || token == "launcher=first")' in policy

cxx=next((x for x in ("clang++-18","clang++","g++") if shutil.which(x)),None)
if not cxx:
    raise SystemExit("C++20 compiler needed for all-on boot policy verification")
src=r"""
#include "dev_launch_policy.h"
#include <cassert>
using Eden::DevLaunch::BootIntent;
int main() {
    // No dev-settings.txt: first launch and restart after PS-button exit.
    static_assert(!BootIntent{}.ShouldAutoboot(false));
    static_assert(!BootIntent{}.ShouldAutoboot(true));
    BootIntent default_build{};
    assert(!default_build.ShouldAutoboot(false));
    assert(!default_build.ShouldAutoboot(false));  // new process, same default
    // Title ID on the build does not imply permission to autoboot.
    default_build.Observe("rom=0100C49025D3E000");
    assert(!default_build.ShouldAutoboot(false));
    BootIntent automatic{};
    automatic.Observe("autoboot=on");
    assert(automatic.ShouldAutoboot(false));
    assert(!automatic.ShouldAutoboot(true));  // a crash always shows notice
    automatic.Observe("launcher=first");
    assert(!automatic.ShouldAutoboot(false));
    automatic.Observe("autoboot=on");
    assert(!automatic.ShouldAutoboot(false)); // forced launcher always wins
    BootIntent disabled{};
    disabled.Observe("autoboot=off");
    disabled.Observe("autoboot=on");
    assert(!disabled.ShouldAutoboot(false));
    BootIntent config{};
    config.Observe("jit_shared=off");
    config.Observe("replay=on");
    assert(!config.ShouldAutoboot(false));
}
"""
with tempfile.TemporaryDirectory(prefix="eden-dev-interactive-boot-") as d:
    cpp=Path(d)/"test.cpp"
    exe=Path(d)/"test"
    cpp.write_text(src)
    subprocess.run([cxx,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(ROOT/"headless"),str(cpp),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print("PASS: first launch, PS-button relaunch, crash and Vulkan recovery open launcher")
print("Explicit autoboot=on only; launcher=first/autoboot=off/crash override")
