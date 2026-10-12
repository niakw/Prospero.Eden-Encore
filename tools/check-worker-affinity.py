#!/usr/bin/env python3
"""Exercise actual native topology discovery/pinning with mocked kernel APIs."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'headless/performance.cpp').read_text();a=s.index('std::array<unsigned, 5> worker_cpus{};');body=s[a:s.index('\n#endif',a)]
code=r'''
#include <array>
#include <algorithm>
#include <atomic>
#include <cstring>
#include <cstdio>
#include <cerrno>
#include <stdexcept>
#include <cassert>
#include <cstdint>
#include <chrono>
#include <thread>
#include <string>
#include "ps5_cpu_topology.h"
using cpuset_t=uint64_t;
#undef CPU_ISSET
#undef CPU_SET
#define CPU_ISSET(c,p) ((*(p)>>(c))&1)
#define CPU_SET(c,p) (*(p)|=uint64_t(1)<<(c))
#define CPU_LEVEL_WHICH 1
#define CPU_WHICH_TID 1
static uint64_t current=0x1fff, fail_mask=0;
static unsigned max_leaf=0xb, level_type=1, apics[64], amd_cores[64];
static bool fail_restore=false, amd_vendor=false, amd_ext_feature=false;
static std::string os_xml;
static int sysctlbyname(const char* name, void* oldp, size_t* oldlen,
                        const void*, size_t) {
 if(std::strcmp(name,"kern.sched.topology_spec") || os_xml.empty()) {
  errno=ENOENT;return -1;
 }
 const size_t length=os_xml.size()+1;
 if(!oldp) {*oldlen=length;return 0;}
 if(*oldlen<length) {errno=ENOMEM;return -1;}
 std::memcpy(oldp,os_xml.c_str(),length);
 *oldlen=length;
 return 0;
}

static constexpr std::array names{"CPUCore_0","CPUCore_1","CPUCore_2","CPUCore_3","GPU"};
static unsigned __get_cpuid_max(unsigned base, void*) {
 return base >= 0x80000000u ? (amd_vendor ? 0x8000001eu : 0x80000000u) : max_leaf;
}
static void mock_cpuid(unsigned leaf,unsigned& a,unsigned& b,unsigned& c,unsigned& d) {
 a=b=c=d=0;
 if(leaf==0) {
  a=max_leaf;
  b=amd_vendor ? 0x68747541u : 0x756e6547u;
  d=amd_vendor ? 0x69746e65u : 0x49656e69u;
  c=amd_vendor ? 0x444d4163u : 0x6c65746eu;
 } else if(leaf==1) {
  a=amd_vendor ? ((8u<<20)|(15u<<8)) : (6u<<8);
 } else if(leaf==0x80000001u) {
  c=amd_ext_feature ? (1u<<22) : 0;
 }
}
static void mock_cpuid_count(unsigned leaf,unsigned subleaf,
                             unsigned& a,unsigned& b,unsigned& c,unsigned& d) {
 (void)subleaf;
 a=b=c=d=0;
 const unsigned cpu=static_cast<unsigned>(__builtin_ctzll(current));
 if(leaf==0x8000001eu) {
  b=(amd_cores[cpu]&255u)|(1u<<8); // two SMT siblings per CoreId
  c=0; // one NUMA node
 } else if(leaf==0xbu) {
  a=1;b=2;c=level_type<<8;d=apics[cpu];
 }
}
#define __cpuid(l,a,b,c,d) mock_cpuid((l),(a),(b),(c),(d))
#define __cpuid_count(l,s,a,b,c,d) mock_cpuid_count((l),(s),(a),(b),(c),(d))
static int cpuset_getaffinity(int,int,int,size_t n,cpuset_t* out){assert(n==8);*out=current;return 0;}
static int cpuset_setaffinity(int,int,int,size_t n,const cpuset_t* in){
 assert(n==8 && *in && !(*in&~0x1fffULL));
 if(*in==fail_mask || (fail_restore && *in==0x1fff)) {errno=22;return -1;}
 current=*in;return 0;
}
'''+body+r'''
int main(){
 for(unsigned i=0;i<64;++i) apics[i]=i;
 CheckWorkerTopology();assert(worker_topology_ready && current==0x1fff);
 assert((worker_cpus==std::array<unsigned,5>{0,2,4,6,8}));
 // Four guest cores + one GPU core: keep their SMT siblings away from
 // secondary shader/IO workers. Only genuinely spare cores 5 and 6 remain.
 assert((secondary_cpus & 0x3ffULL) == 0);
 assert(secondary_cpus == (0x1fffULL & ~0x3ffULL));
 cpuset_t allowed=current;PinWorker(4,allowed);assert(current==256 && allowed==256);
 // The probe's process-wide CPU set decides, not a narrower mask the thread inherited.
 current=0x1fff;allowed=3;PinWorker(4,allowed);assert(current==256 && allowed==256);
 current=0x1fff;
 PinWorker(5,allowed);assert(current==0x1fff);
 for(unsigned i=0;i<7;++i) apics[i]=i*2;
 for(unsigned i=7;i<13;++i) apics[i]=(i-7)*2+1;
 CheckWorkerTopology();assert((worker_cpus==std::array<unsigned,5>{0,1,2,3,4}) && current==0x1fff);
 current=3;CheckWorkerTopology();assert(!worker_topology_ready && current==3);
 current=0x1fff;fail_mask=4;CheckWorkerTopology();assert(!worker_topology_ready && current==0x1fff);
 fail_mask=0;level_type=0;CheckWorkerTopology();assert(!worker_topology_ready && current==0x1fff);
 level_type=1;CheckWorkerTopology();assert(worker_topology_ready);
 fail_mask=16;allowed=current;PinWorker(4,allowed);assert(allowed==0x1fff && current==0x1fff);
 fail_mask=0;fail_restore=true;bool threw=false;
 try{CheckWorkerTopology();}catch(const std::runtime_error&){threw=true;}
 assert(threw);

 // PS5 Zen-family extended-topology path: x2APIC is unavailable, but
 // authenticated AMD vendor/family/TopologyExtensions still prove distinct
 // physical cores. Two sibling logical CPUs share the same physical CoreId.
 fail_restore=false;current=0x1fff;max_leaf=0xa;
 amd_vendor=true;amd_ext_feature=true;
 for(unsigned i=0;i<13;++i) amd_cores[i]=i/2;
 CheckWorkerTopology();
 assert(worker_topology_ready && current==0x1fff);
 assert((worker_cpus==std::array<unsigned,5>{0,2,4,6,8}));
 // FW13.60 regression: AMD leaf presents 13 unique "cores" for 13 logical
 // CPUs, but the authenticated x2APIC SMT shift still identifies 7 physical.
 max_leaf=0xb;amd_ext_feature=true;
 for(unsigned i=0;i<13;++i) {amd_cores[i]=i;apics[i]=i;}
 CheckWorkerTopology();
 assert(worker_topology_ready && current==0x1fff);
 assert((worker_cpus==std::array<unsigned,5>{0,2,4,6,8}));
 assert(cpu_core[0]==cpu_core[1] && cpu_core[2]!=cpu_core[0]);
 // Both leaves implausible: MUST retain the unpinned logical fallback.
 for(unsigned i=0;i<13;++i) apics[i]=i*2;
 CheckWorkerTopology();
 assert(!worker_topology_ready && current==0x1fff);
 assert((worker_cpus==std::array<unsigned,5>{0,0,0,0,0}));
 max_leaf=0xa;
 // PS5's 13 visible CPUs are seven OS-reported physical SMT groups.
 // CPUID is intentionally broken in BOTH AMD and x2APIC representations.
 max_leaf=0xb;amd_vendor=true;amd_ext_feature=true;
 for(unsigned i=0;i<13;++i) {amd_cores[i]=i;apics[i]=0;}
 os_xml="<groups><group level=\"1\"><children>";
 for(unsigned i=0;i<14;i+=2) {
  char pair[150];
  std::snprintf(pair,sizeof(pair),
    "<group level=\"2\"><cpu count=\"2\" mask=\"%llx,0,0\">pair</cpu>"
    "<flags><flag name=\"SMT\">SMT group</flag></flags></group>",
    (unsigned long long)(3ULL<<i));
  os_xml+=pair;
 }
 os_xml+="</children></group></groups>";
 CheckWorkerTopology();
 assert(worker_topology_ready && current==0x1fff);
 assert((worker_cpus==std::array<unsigned,5>{0,2,4,6,8}));
 assert(secondary_cpus==(0x1fffULL & ~0x3ffULL));
 // Invalid OS XML cannot turn a broken CPUID reading into physical proof.
 os_xml="<groups><group><cpu count=\"2\" mask=\"3\"></cpu>"
        "<flags><flag name=\"SMT\"></flag></flags></group></groups>";
 CheckWorkerTopology();
 assert(!worker_topology_ready && current==0x1fff);
 os_xml.clear();
 max_leaf=0xa;
 // TopologyExtensions absent: do not claim proof from logical IDs alone.
 amd_ext_feature=false;
 CheckWorkerTopology();
 assert(!worker_topology_ready && topology_allowed_valid);
 assert(current==0x1fff);
 assert((worker_cpus==std::array<unsigned,5>{0,0,0,0,0}));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    exe=Path(tmp)/'affinity'
    subprocess.run(['c++','-std=c++20','-I',str(root/'headless'),'-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-x','c++','-','-o',str(exe)],input=code,text=True,check=True)
    subprocess.run([str(exe)],check=True)
print('Worker topology: PASS OS scheduler SMT groups, broken CPUID fallback and readback/restoration (host only)')
