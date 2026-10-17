#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real-source C++ waiter-list alias witness; native header keeps typed links.

Shows original strict-aliasing optimized misbehavior for head/middle/tail
removals, verifies safe native path and traversal-after-unlink semantics.
Host only; never a console/gameplay freeze proof.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
pinned=(root/"vendor/sources/eden/src/core/hle/kernel/k_synchronization_object.h").read_text()
native=(root/"vendor/encore-active/eden-sync/src/core/hle/kernel/k_synchronization_object.h").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
workflow=(root/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-native-hle-sync-unlink-host.py" in workflow
assert "EDEN_NATIVE_SYNC_HEADER_ROOT" in cmake
assert "target_include_directories(core BEFORE PUBLIC" in cmake

old="""        ThreadListNode* prev_ptr =
            reinterpret_cast<ThreadListNode*>(std::addressof(m_thread_list_head));
        ThreadListNode* prev_val = nullptr;
        ThreadListNode *prev, *tail_prev;

        do {
            prev = prev_ptr;
            prev_ptr = prev_ptr->next;
            tail_prev = prev_val;
            prev_val = prev_ptr;
        } while (prev_ptr != node_);

        if (m_thread_list_tail == node_) {
            m_thread_list_tail = tail_prev;
        }

        prev->next = node_->next;"""
fix="""        // Follow the real pointer links; casting the address of the head
        // pointer to a ThreadListNode object violates C++ aliasing rules.
        ThreadListNode** link = std::addressof(m_thread_list_head);
        ThreadListNode* previous = nullptr;
        while (*link != node_) {
            ASSERT(*link != nullptr);
            previous = *link;
            link = std::addressof((*link)->next);
        }

        if (m_thread_list_tail == node_) {
            m_thread_list_tail = previous;
        }

        // Preserve node_->next: NotifyAvailable can still be walking the
        // removed node until its scheduler-locked iteration completes.
        *link = node_->next;"""
assert pinned.count(old)==1
assert native==pinned.replace(old,fix),"native header differs beyond checked alias fix"

def extract(text,start,end):
    assert text.count(start)==1 and text.count(end)==1
    return start+text.split(start,1)[1].split(end,1)[0].rstrip()+"\n\n"

header=r"""
#include <cassert>
#include <cstdio>
#include <memory>
struct KThread;
#define ASSERT(x) assert(x)
struct SyncObject {
    struct ThreadListNode {ThreadListNode* next{};KThread* thread{};};
"""
footer=r"""
    ThreadListNode* m_thread_list_head{};
    ThreadListNode* m_thread_list_tail{};
};
int main(){
 for(int n=0;n<3000;n++){
  SyncObject l;SyncObject::ThreadListNode v[4]{};
  for(auto& x:v)l.LinkNode(&x);
  l.UnlinkNode(&v[1]);assert(l.m_thread_list_head==&v[0]);assert(v[0].next==&v[2]);
  l.UnlinkNode(&v[0]);assert(l.m_thread_list_head==&v[2]);
  l.UnlinkNode(&v[3]);assert(l.m_thread_list_tail==&v[2]);
  l.UnlinkNode(&v[2]);assert(!l.m_thread_list_head&&!l.m_thread_list_tail);
 }
 {
  SyncObject l;SyncObject::ThreadListNode v[4]{};
  for(auto& x:v)l.LinkNode(&x);
  for(auto* cur=l.m_thread_list_head;cur;cur=cur->next){
   if(cur==&v[0]){l.UnlinkNode(&v[0]);l.UnlinkNode(&v[1]);}
   else if(cur==&v[2])l.UnlinkNode(&v[2]);
   else if(cur==&v[3])l.UnlinkNode(&v[3]);
  }
  assert(!l.m_thread_list_head&&!l.m_thread_list_tail);
 }
 std::puts("SYNC_LIST_LINKED_NODES_PASS");
}
"""
def methods(source):
    return (extract(source,"    void LinkNode(","    void UnlinkNode(")
           +extract(source,"    void UnlinkNode(","\nprotected:"))

compilers=[c for c in (shutil.which("g++"),shutil.which("clang++")) if c]
assert compilers
witnesses=0
with tempfile.TemporaryDirectory(prefix="encore-native-synclist-") as td:
    tmp=Path(td)
    for label,code in (("pinned",pinned),("native",native)):
        cpp=tmp/(label+".cpp")
        cpp.write_text(header+methods(code)+footer)
        for compiler in compilers:
            for level in (0,1,2,3):
                exe=tmp/(label+"-"+Path(compiler).name+"-"+str(level))
                subprocess.run([compiler,"-std=c++20","-O"+str(level),
                    "-fstrict-aliasing","-Wall","-Wextra","-Werror",
                    str(cpp),"-o",str(exe)],check=True,timeout=30)
                result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
                if label=="native" or level==0:
                    assert result.returncode==0,(label,compiler,level,result.stderr)
                elif result.returncode!=0:
                    witnesses+=1
                print(label,Path(compiler).name,"O"+str(level),
                      "ALIAS_WITNESS" if label=="pinned" and result.returncode else "PASS")
assert witnesses>=1,"Original optimizer alias witness not observed on host compilers"
print("PINNED_SYNC_LIST_ALIAS_OPTIMIZED_FAILURE_WITNESS_PASS")
print("NATIVE_SYNC_LIST_TYPED_UNLINK_HOST_PASS")
print("SYNC_LIST_HOST_ONLY_NO_CONSOLE_OR_FREEZE_PROOF")
