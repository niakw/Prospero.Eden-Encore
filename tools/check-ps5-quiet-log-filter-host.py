#!/usr/bin/env python3
"""Native only: avoid formatting a disabled console log backend; keep toggle live."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-core/src/common/logging.cpp").read_text()
routine=src.split("void FmtLogMessageImpl(",1)[1]
guard=routine.split("#ifdef __OPENORBIS__",1)[1].split("#endif",1)[0]
assert "color_console_backend.enabled.load(std::memory_order_relaxed)" in guard
assert "return;" in guard
assert routine.index("#ifdef __OPENORBIS__") < routine.index("fmt::vformat_to_n")
assert "if (logging_instance && logging_instance->filter.CheckMessage" in routine
assert src.count("#ifdef __OPENORBIS__")>=1
assert "std::atomic_bool enabled = false;" in src
cc=shutil.which("clang++-18") or shutil.which("clang++")
assert cc
cpp=r"""
#include <atomic>
#include <cassert>
#include <optional>
struct Console {std::atomic_bool enabled{false};};
struct Backend {Console color_console_backend;};
std::optional<Backend> logging_instance{};
unsigned formatted=0;
void Emit() {
#ifdef __OPENORBIS__
__ACTUAL_GUARD__
#endif
 if(logging_instance) ++formatted;
}
int main(){
 logging_instance.emplace();
 for(int i=0;i<1000;++i) Emit();
 assert(formatted==0);
 logging_instance->color_console_backend.enabled.store(true);
 Emit();assert(formatted==1);
 logging_instance->color_console_backend.enabled.store(false);
 Emit();assert(formatted==1);
 logging_instance.reset();Emit();assert(formatted==1);
}
""".replace("__ACTUAL_GUARD__",guard)
with tempfile.TemporaryDirectory(prefix="eden-quiet-logger-") as tmp:
 d=Path(tmp)
 (d/"check.cpp").write_text(cpp)
 subprocess.run([cc,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
  "-fsanitize=address,undefined","-fno-sanitize-recover=all",
  "-D__OPENORBIS__","-pthread",str(d/"check.cpp"),"-o",str(d/"check")],
  check=True,timeout=90)
 subprocess.run([str(d/"check")],check=True,timeout=90)
print("NATIVE_QUIET_LOG_HOST_PASS no_format_when_off=1 toggle_on=1 toggle_off=1")
