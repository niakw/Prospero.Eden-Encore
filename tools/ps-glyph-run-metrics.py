#!/usr/bin/env python3
"""Count actual provider calls, blocks, results and candidate links, not queued URLs.

Runs on a bounded batch of small result JSON files. No source downloads or
account credentials are retained. Never claims missing searches completed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

def summarize(docs:list[dict],run_id:str)->dict:
    rows=[]
    for batch in docs:
        if batch.get("schema")!=1 or not isinstance(batch.get("games"),list):
            raise ValueError("unknown search batch data")
        # Older reports lack the precise counters; derive from explicit
        # completed game records and the provider errors only in that case.
        successful=sum(1 for x in batch["games"]
                       if x.get("discovery_status","").startswith("searched_"))
        errors=batch.get("errors",[])
        if not isinstance(errors,list) or len(errors)>100:
            raise ValueError("invalid provider error count")
        completed=batch.get("requests_completed",successful)
        attempted=batch.get("requests_attempted",completed+len(errors))
        if not all(type(x) is int and 0<=x<=250 for x in (completed,attempted)):
            raise ValueError("unbounded provider counters")
        if not completed<=attempted or attempted>completed+len(errors):
            raise ValueError("inconsistent requests attempted/completed")
        rows.append({
            "provider":batch.get("provider","unknown"),
            "completed":completed,"attempted":attempted,
            "blocked_or_failed":len(errors),
            "source_leads":batch.get("source_leads",0),
            "first_block_reason":str(errors[0].get("reason",""))[:120] if errors else None,
            "sampled_title_ids":[x["title_id"] for x in batch["games"][:3]],
        })
    return {
        "schema":1,"run_id":str(run_id)[:80],
        "total_attempts":sum(x["attempted"] for x in rows),
        "total_completed":sum(x["completed"] for x in rows),
        "total_blocked_or_failed":sum(x["blocked_or_failed"] for x in rows),
        "source_leads_observed":sum(x["source_leads"] for x in rows),
        "providers":rows,
        "note":"A completed search query is not a confirmed mod; counts exclude offline URL preparation."
    }

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--batches",nargs="+",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--run-id",required=True)
    a=p.parse_args()
    try:
        if a.out.exists() or a.out.is_symlink() or not a.out.parent.is_dir():
            raise ValueError("output already exists")
        docs=[]
        for file in a.batches:
            if (not file.is_file() or file.is_symlink() or
                file.stat().st_size>64*1024*1024):
                raise ValueError("unsafe batch report")
            docs.append(json.loads(file.read_text("utf-8")))
        doc=summarize(docs,a.run_id)
        a.out.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n")
        print("EXECUTED GLYPH MOD REQUESTS",doc["total_completed"],"/",
              doc["total_attempts"],"attempted;",doc["total_blocked_or_failed"],
              "failed/blocked,",doc["source_leads_observed"],"source leads")
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print("INVALID DISCOVERY REQUEST METRICS:",exc,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
