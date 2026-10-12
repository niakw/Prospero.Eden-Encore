#!/usr/bin/env python3
"""R379: actual FreeBSD 11.4 ULE XML masks and SMT/HTT flag variants."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
header=(root/'headless/ps5_cpu_topology.h').read_text()
assert 'FreeBsdMask(' in header
assert 'name=\\"SMT\\"' in header and 'name=\\"HTT\\"' in header
assert 'word != 0' in header
code=r"""
#include <cassert>
#include <string>
#include <array>
#include <cstdio>
#include "ps5_cpu_topology.h"
using Eden::CpuTopology::ParseSmtGroups;
using Eden::CpuTopology::FreeBsdMask;
std::string Xml(bool htt, bool mix, bool thread_only=false) {
    std::string xml="<groups>\n <group level=\"1\" cache-level=\"0\">\n"
                    " <cpu count=\"13\" mask=\"1fff,0,0,0\">all</cpu>\n"
                    " <children>\n";
    for(unsigned i=0;i<7;++i) {
        const unsigned long long mask=3ULL<<(2*i);
        char raw[100];
        std::snprintf(raw,sizeof(raw),"%llx,0,0,0",mask);
        xml+="<group level=\"2\" cache-level=\"1\">\n";
        xml+="<cpu count=\"2\" mask=\""+std::string(raw)+"\">siblings</cpu>\n";
        xml+="<flags><flag name=\"THREAD\">THREAD group</flag>";
        if(!thread_only) {
            const bool as_htt=htt && (!mix || i%2==0);
            xml+=as_htt?"<flag name=\"HTT\">HTT group</flag>"
                       :"<flag name=\"SMT\">SMT group</flag>";
        }
        xml+="</flags></group>\n";
    }
    xml+="</children></group></groups>\n";
    return xml;
}
int main(){
    constexpr unsigned long long allowed=0x1fff;
    std::array<int,64> ids{};
    auto expect=[&](const std::string& xml, bool ok) {
        assert(ParseSmtGroups(xml,allowed,ids)==ok);
        if(ok) {
            for(unsigned i=0;i<13;++i)
                assert(ids[i]==int(i&~1u)); // 13 allowed CPUs, 7 siblings
        } else {
            for(int id:ids)assert(id==-1);
        }
    };
    expect(Xml(false,false),true);
    expect(Xml(true,false),true);
    expect(Xml(true,true),true);
    expect(Xml(true,false,true),false); // umbrella THREAD != sibling proof
    std::string invalid=Xml(true,false);
    auto at=invalid.find("mask=\"3,0,0,0\"");
    assert(at!=std::string::npos);
    invalid.replace(at,strlen("mask=\"3,0,0,0\""),"mask=\"3,1,0,0\"");
    expect(invalid,false); // high CPU bits must not be ignored
    std::string duplicate=Xml(true,false);
    at=duplicate.find("mask=\"c,0,0,0\"");
    assert(at!=std::string::npos);
    duplicate.replace(at,strlen("mask=\"c,0,0,0\""),"mask=\"3,0,0,0\"");
    expect(duplicate,false); // duplicate sibling group
    std::uint64_t mask=0;
    assert(FreeBsdMask("1fff,0,0,0",mask) && mask==allowed);
    assert(FreeBsdMask("1FFF",mask) && mask==allowed);
    assert(!FreeBsdMask("3,1",mask));
    assert(!FreeBsdMask("3,",mask));
    assert(!FreeBsdMask(",3",mask));
    assert(!FreeBsdMask("3,zz",mask));
}
"""
code=code.replace("#include <cstdio>","#include <cstdio>\n#include <cstring>")
env=os.environ.copy()
if sys.platform=='darwin' and not env.get('SDKROOT'):
    sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
    if sdk.is_dir():env['SDKROOT']=str(sdk)
with tempfile.TemporaryDirectory(prefix='eden-r379-ule11-') as td:
    source=Path(td)/'topology.cpp'
    target=Path(td)/'topology'
    source.write_text(code)
    subprocess.run(['c++','-std=c++20','-O1','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-I',str(root/'headless'),
                    str(source),'-o',str(target)],check=True,env=env,timeout=30)
    subprocess.run([str(target)],check=True,env=env,timeout=12)
print('PASS R379 actual FreeBSD 11.4 HTT/SMT cpuset XML: 7 sibling groups, wrong/partial/upper bits rejected')
