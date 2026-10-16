#!/usr/bin/env python3
"""Host ASan/UBSan: source-derived cache title ID segregation, with negative control."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/core/file_sys/savedata_factory.cpp").read_text()
active = (root / "vendor/encore-active/eden-core/src/core/file_sys/savedata_factory.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
old = "if (type == SaveDataType::Account || type == SaveDataType::Device) {"
new = "if (type == SaveDataType::Account || type == SaveDataType::Device ||\n        type == SaveDataType::Cache) {"
assert pinned.count(old) == 1
assert active == pinned.replace(old, new)
assert cmake.count('list(REMOVE_ITEM eden_savedata_sources "file_sys/savedata_factory.cpp")') == 1
assert cmake.count('list(APPEND eden_savedata_sources "') == 1
assert "EDEN_MAINTAINED_SAVEDATA" in cmake
head = "std::string SaveDataFactory::GetFullPath("
tail = "\nstd::string SaveDataFactory::GetUserGameSaveDataRoot("
assert pinned.count(head) == active.count(head) == 1
def extract(source):
    return head + source.split(head, 1)[1].split(tail, 1)[0]

body = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <type_traits>
using u64 = std::uint64_t;
using u8 = std::uint8_t;
using u128 = std::array<u64, 2>;
#define LOG_INFO(...) ((void)0)
#define ASSERT_MSG(...) assert(false)
namespace fmt {
template <typename T> std::string Value(const T& v) {
  if constexpr (std::is_integral_v<T>) {
    std::ostringstream o;
    o << std::uppercase << std::hex << std::setfill('0') << std::setw(16) << v;
    return o.str();
  } else {
    return std::string(v);
  }
}
template <typename... Ts> std::string format(const char* p, const Ts&... vs) {
  const std::array<std::string, sizeof...(Ts)> args{Value(vs)...};
  std::string out;
  std::size_t cursor=0, arg=0;
  while (p[cursor]) {
    if (p[cursor] != '{') { out += p[cursor++]; continue; }
    auto close = cursor+1;
    while (p[close] && p[close] != '}') ++close;
    assert(p[close] == '}' && arg < args.size());
    out += args[arg++];
    cursor = close + 1;
  }
  assert(arg == args.size());
  return out;
}
}
namespace FileSys {
enum class SaveDataSpaceId { System, User, SdUser, Temporary };
enum class SaveDataType { System, Account, Device, Temporary, Cache };
struct Dir { std::shared_ptr<Dir> GetDirectoryRelative(const std::string&) { return {}; } };
using VirtualDir=std::shared_ptr<Dir>;
using ProgramId=u64;
std::string GetFutureSaveDataPath(SaveDataSpaceId, SaveDataType, u64, u128) { return ""; }
struct SaveDataFactory {
  static std::string GetFullPath(ProgramId, VirtualDir, SaveDataSpaceId, SaveDataType, u64, u128, u64);
  static std::string GetSaveDataSpaceIdPath(SaveDataSpaceId s) {
    return s == SaveDataSpaceId::Temporary ? "/temp/" : "/user/";
  }
};
__METHOD__
}
int main() {
 using namespace FileSys;
 constexpr ProgramId a=0x01007EF00011E000ULL, b=0x0100C49025D3E000ULL;
 const u128 user{0,0};
 const auto path=[&](ProgramId p, SaveDataType t, u64 id) {
   return SaveDataFactory::GetFullPath(p,nullptr,SaveDataSpaceId::User,t,id,user,0);
 };
 const auto a0=path(a,SaveDataType::Cache,0);
 const auto b0=path(b,SaveDataType::Cache,0);
#ifdef PINNED_LEGACY
 assert(a0 == b0 && a0 == "/user/save/cache/0000000000000000");
#else
 assert(a0 != b0);
 assert(a0 == "/user/save/cache/01007EF00011E000");
 assert(b0 == "/user/save/cache/0100C49025D3E000");
#endif
 const auto explicit_a=path(a,SaveDataType::Cache,0x1234);
 assert(explicit_a == path(b,SaveDataType::Cache,0x1234));
 assert(explicit_a == "/user/save/cache/0000000000001234");
 for(const auto type : {SaveDataType::Account, SaveDataType::Device}) {
   assert(path(a,type,0)==path(a,type,a));
   assert(path(a,type,0)!=path(b,type,0));
 }
 assert(path(a,SaveDataType::Temporary,0)==path(b,SaveDataType::Temporary,0));
 assert(path(a,SaveDataType::System,0)==path(b,SaveDataType::System,0));
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "Host Clang required"
with tempfile.TemporaryDirectory(prefix="encore-title-cache-") as dir:
    tmp=Path(dir)
    for label, source, flags in (("pinned", pinned, ["-DPINNED_LEGACY"]),
                                 ("maintained", active, [])):
        src=tmp / (label+".cpp")
        exe=tmp / label
        src.write_text(body.replace("__METHOD__",extract(source)))
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        *flags,str(src),"-o",str(exe)],check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=30)
print("TITLE_CACHE_STORAGE_HOST_PASS pinned_shared=1 isolated=1 explicit_id=1 save_compat=1 source_parity=1")
