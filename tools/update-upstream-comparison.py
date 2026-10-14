#!/usr/bin/env python3
"""Refresh pinned dependency comparisons without modifying dependency versions."""
import argparse
import datetime as datetime
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"docs/UPSTREAM_GAP_REGISTER_2026-10-14.md"
START="<!-- BEGIN AUTO-UPSTREAM-COMPARISON -->"
END="<!-- END AUTO-UPSTREAM-COMPARISON -->"

def sources():
    items=json.loads((ROOT/"tools/deps.json").read_text())["items"]
    result=[]
    for item in items:
        url=item.get("url") or ""
        parsed=urllib.parse.urlparse(url)
        parts=parsed.path.strip("/").split("/")
        repo=parts[0]+"/"+parts[1].removesuffix(".git") if parsed.hostname=="github.com" and len(parts)>1 else ""
        ref=item.get("commit") or ""
        if not ref and repo and len(parts)>3 and parts[2]=="archive":
            tail=parts[3:]
            if tail[:2]==["refs","tags"]:
                tail=tail[2:]
            ref="/".join(tail).removesuffix(".tar.gz").removesuffix(".zip")
        if "/releases/download/" in parsed.path:
            ref=""
        result.append((item["name"],repo if ref else "",ref))
    return result

def fetch(path):
    token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token: raise RuntimeError("GitHub token required")
    req=urllib.request.Request("https://api.github.com/"+path,headers={
        "Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28","User-Agent":"encore-upstream-check"})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code in (404,409,422):
            return {"error_status":e.code}
        raise RuntimeError("GitHub API "+str(e.code)+" for "+path) from e

def compare(rows,api=fetch):
    output=[]
    for name,repo,ref in rows:
        if not repo:
            output.append((name,"frozen archive / binary",ref or "—","—","not comparable"))
            continue
        meta=api("repos/"+repo)
        if "error_status" in meta:
            output.append((name,repo,ref[:12],"—","repository unavailable"))
            continue
        branch=meta["default_branch"]
        encoded=urllib.parse.quote(ref,safe="")+"..."+urllib.parse.quote(branch,safe="")
        data=api("repos/"+repo+"/compare/"+encoded+"?per_page=100")
        if "error_status" in data:
            output.append((name,repo,ref[:12],"—","comparison unavailable"))
            continue
        ahead,behind=data.get("ahead_by"),data.get("behind_by")
        if not isinstance(ahead,int) or not isinstance(behind,int):
            raise RuntimeError("Malformed response "+repo)
        status="identical" if ahead==behind==0 else "diverged" if behind else "upstream ahead"
                # Commit messages remain untrusted upstream text: sanitize before rendering.
        important=("kernel","schedul","mutex","lock","memory","heap","guest","jit",
                   "dynarmic","cache","shader","texture","gpu","vulkan","radv",
                   "buffer","hid","controller","input","save","fs","sync","thread",
                   "frame","fence","alloc","compil","driv","fix","hang","freeze")
        notable=[]
        for item in data.get("commits",[]):
            raw=item.get("commit",{}).get("message","").splitlines()
            title=raw[0] if raw else ""
            if any(term in title.lower() for term in important):
                title=title.replace("|","/").replace("[","(").replace("]",")")
                title=title.replace("<","").replace(">","").replace("`","'")[:115]
                notable.append((item.get("sha","")[:12],title))
        limit=45 if name=="eden" else 20 if name in ("ps5-mesa","ps5-payload-sdk-fork","opengl-source") else 8
        output.append((name,repo,ref[:12],f"+{ahead} / -{behind}",status,
                       notable[-limit:],ahead>len(data.get("commits",[]))))
        print(name,repo,output[-1][3],status,flush=True)
    return output

def section(rows,stamp):
    lines=[START,"### Automated comparison (daily + manual)","",
       "Checked in UTC: **"+stamp+"**. Changes are commits relative to pins, not proven missing fixes.",
       "This workflow never imports source patches, modifies dependencies, or reads console data.","",
       "| Dependency | Source | Pinned revision | Ahead / behind | Status |",
       "|---|---|---|---:|---|"]
    for row in rows:
        name,repo,ref,delta,status=row[:5]
        source=("["+repo+"](https://github.com/"+repo+")") if "/" in repo else repo
        lines.append("| "+name+" | "+source+" | "+ref+" | "+delta+" | "+status+" |")
        lines.extend(["","### Source changes requiring review","",
                  "These are upstream commit titles, not validated Encore integrations."])
    for row in rows:
        if len(row)<7 or not row[5]:continue
        name,repo=row[:2]
        lines.append("")
        lines.append("**"+name+"**"+(" (history excerpt; some commits omitted)" if row[6] else ""))
        for sha,title in row[5]:
            if sha:
                lines.append("- ["+sha+"](https://github.com/"+repo+"/commit/"+sha+") — "+title)
    lines.extend(["","Unavailable comparisons are not equivalent to zero changes.",
                  "The API can truncate changed-file lists beyond 300 files.",END])
    return "\n".join(lines)

def update(text,new):
    if text.count(START)!=text.count(END) or text.count(START)>1:
        raise RuntimeError("Malformed report markers")
    if START in text:
        text=text[:text.index(START)]+text[text.index(END)+len(END):]
    return text.rstrip()+"\n\n"+new+"\n"

def test():
    rows=sources()
    assert len(rows)==22 and len(set(x[0] for x in rows))==22
    assert next(x for x in rows if x[0]=="eden")[2].startswith("5f142c")
    assert next(x for x in rows if x[0]=="fmt")[2]=="12.1.0"
    assert next(x for x in rows if x[0]=="pacbrew")[1]==""
    demo=[("demo","owner/repo","aaa","+2 / -1","diverged")]
    x=update("Existing notes",section(demo,"2026-10-14"))
    y=update(x,section(demo,"2026-10-15"))
    assert y.count(START)==y.count(END)==1 and "2026-10-14" not in y
    print("UPSTREAM_DAILY_SELFTEST_PASS source_count=22")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--refresh",action="store_true")
    args=p.parse_args()
    if args.self_test:
        test()
    elif args.refresh:
        rows=compare(sources())
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        REPORT.write_text(update(REPORT.read_text(),section(rows,stamp)))
        print("UPSTREAM_DAILY_REFRESH_PASS",len(rows),stamp)
    else:
        p.error("choose --self-test or --refresh")
