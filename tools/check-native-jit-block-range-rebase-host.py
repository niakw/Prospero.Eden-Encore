#!/usr/bin/env python3
"""Source-selected C++ regression: JIT invalidation retires cross-page aliases."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
impl=(root/"vendor/encore-active/eden-core/src/dynarmic/backend/block_range_information.cpp").read_text()
start="template<typename P>\nvoid BlockRangeInformation<P>::AddRange("
end="template class BlockRangeInformation<u32>;"
assert impl.count(start)==impl.count(end)==1
body=impl[impl.index(start):impl.index(end)]
for invariant in ("purge_pages.push_back(owner_page);",
                  "std::sort(purge_pages.begin(), purge_pages.end());",
                  "erase_locations.find(entry.location)", "pages.erase(it);"):
    assert invariant in body
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
program=r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <functional>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <boost/icl/interval_set.hpp>
using u32=std::uint32_t;
using u64=std::uint64_t;
namespace Dynarmic::IR {
struct LocationDescriptor {
    u64 value{};
    bool operator==(const LocationDescriptor& rhs) const {return value==rhs.value;}
};
}
namespace std {
template<> struct hash<Dynarmic::IR::LocationDescriptor> {
    size_t operator()(const Dynarmic::IR::LocationDescriptor& x) const noexcept {
        return hash<u64>{}(x.value);
    }
};
}
namespace Common {
template<class K,class V>using unordered_map=std::unordered_map<K,V>;
template<class K>using unordered_set=std::unordered_set<K>;
}
namespace Dynarmic::Backend {
template<class P> class BlockRangeInformation {
public:
    void AddRange(boost::icl::discrete_interval<P>,IR::LocationDescriptor);
    void ClearCache();
    ::Common::unordered_set<IR::LocationDescriptor>
        InvalidateRanges(const boost::icl::interval_set<P>&);
    size_t BucketSize(P page) const {
        const auto it=pages.find(page);
        return it==pages.end()?0:it->second.size();
    }
private:
    struct Entry { P first,last; IR::LocationDescriptor location; };
    static constexpr unsigned page_bits=12;
    ::Common::unordered_map<P,std::vector<Entry>> pages;
};
__ACTUAL_METHODS__
}
using Dynarmic::Backend::BlockRangeInformation;
using Dynarmic::IR::LocationDescriptor;
template<class P>
static boost::icl::interval_set<P> Range(P first,P last){
    boost::icl::interval_set<P> set;
    set.add(boost::icl::discrete_interval<P>::closed(first,last));
    return set;
}
int main() {
    BlockRangeInformation<u64> c;
    const LocationDescriptor a{17},b{23},s{29};
    c.AddRange(boost::icl::discrete_interval<u64>::closed(0x1ff0,0x2040),a);
    c.AddRange(boost::icl::discrete_interval<u64>::closed(0x2080,0x20ff),b);
    assert(c.BucketSize(1)==1 && c.BucketSize(2)==2);
    const auto old=c.InvalidateRanges(Range<u64>(0x1ff0,0x1fff));
    assert(old.size()==1 && old.contains(a));
    // In the old implementation page 2 still owned descriptor 'a'.
    assert(c.BucketSize(1)==0 && c.BucketSize(2)==1);
    c.AddRange(boost::icl::discrete_interval<u64>::closed(0x1000,0x107f),a);
    const auto stale=c.InvalidateRanges(Range<u64>(0x2010,0x2030));
    assert(stale.empty());
    assert(c.BucketSize(1)==1 && c.BucketSize(2)==1);
    const auto real=c.InvalidateRanges(Range<u64>(0x2080,0x2090));
    assert(real.size()==1 && real.contains(b));
    assert(c.BucketSize(2)==0);
    c.AddRange(boost::icl::discrete_interval<u64>::closed(0x2ff0,0x4010),s);
    assert(c.BucketSize(2)==1 && c.BucketSize(3)==1 && c.BucketSize(4)==1);
    auto overlap=Range<u64>(0x2ff0,0x3000);
    overlap.add(boost::icl::discrete_interval<u64>::closed(0x3008,0x300c));
    const auto hits=c.InvalidateRanges(overlap);
    assert(hits.size()==1 && hits.contains(s));
    assert(c.BucketSize(2)==0 && c.BucketSize(3)==0 && c.BucketSize(4)==0);
    c.ClearCache();
    assert(c.BucketSize(1)==0 && c.BucketSize(2)==0);
}
""".replace("__ACTUAL_METHODS__",body)
with tempfile.TemporaryDirectory(prefix="encore-jit-range-rebase-") as tmp:
    cpp=Path(tmp)/"range.cpp"
    cpp.write_text(program)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/("range"+opt)
        subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined",str(cpp),"-o",str(exe)],
                       check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=20)
        print("JIT_BLOCK_RANGE_REBASE_HOST_PASS",opt)
