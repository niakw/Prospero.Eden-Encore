#!/usr/bin/env python3
"""R386 offline FC27 freeze signature finder (NO PS5 builds or console writes).

A long stretch of identical five-second draw/write/IPC ratios despite a live
GPU suggests repeated workload, NOT provably unchanged pixels or game state.

usage: python3 tools/analyze-fc27-frozen-workload.py heap.log [stderr.log]
       python3 tools/analyze-fc27-frozen-workload.py --self-test
"""
import json
import re
import statistics
import sys
from pathlib import Path

VALUES = re.compile(r'([A-Za-z_][A-Za-z_0-9]*)=(-?\d+(?:\.\d+)?)')

def parse(line):
    return {k: float(v) if '.' in v else int(v) for k, v in VALUES.findall(line)}

def analyze(heap_text, stderr_text=''):
    groups = {
        'frame': [],
        'gpu': [],
        'guest': [],
        'early': [],
    }
    names = {
        'EDEN_VULKAN_FRAME frames=':'frame',
        'EDEN_DEV_GPU frame=':'gpu',
        'EDEN_DEV_GUEST cpu_write_calls=':'guest',
        'EDEN_SCHEDULER_PREFLIGHT frame=':'early',
    }
    core_epochs = {}
    sha = re.search(r'EDEN_BUILD_SOURCE source_sha=([0-9a-f]{40})',heap_text)
    for line in heap_text.splitlines():
        for prefix,name in names.items():
            if line.startswith(prefix):
                groups[name].append(parse(line))
                break
        if line.startswith('EDEN_PERF_CPU_POINT core='):
            point=parse(line)
            if 'core' in point and 'epoch' in point:
                core_epochs[point['core']]=point['epoch']
    length=min(map(len, (groups['frame'],groups['gpu'],groups['guest'])))
    if length<2:
        raise ValueError('Need at least two complete five-second diagnostic windows')
    ratios=[]
    for i in range(1,length):
        now,old=groups['gpu'][i],groups['gpu'][i-1]
        g,p=groups['guest'][i],groups['guest'][i-1]
        frame=groups['frame'][i]
        drawn=now['frame']-old['frame']
        if drawn<=0: continue
        row={
            'frame': now['frame'],
            'fps':frame['fps'],
            'late50':frame['late50'],
            'draws':(now['draws']-old['draws'])/drawn,
            'writes':(g['cpu_write_calls']-p['cpu_write_calls'])/drawn,
            'ipc':(g['ipc_calls']-p['ipc_calls'])/drawn,
        }
        if i<len(groups['early']):
            row['early']=(groups['early'][i]['dispatched']-groups['early'][i-1]['dispatched'])/drawn
        ratios.append(row)
    if len(ratios)<10: raise ValueError('Need 10 windows to establish a reference')
    keys=('draws','writes','ipc')
    tail=ratios[-10:]
    reference={k:statistics.median(row[k] for row in tail) for k in keys}
    stable=[]
    for row in reversed(ratios):
        if not (29.8<=row['fps']<=30.2 and row['late50']==0):
            break
        if any(abs(row[k]-reference[k]) > .025*max(1,abs(reference[k])) for k in keys):
            break
        stable.append(row)
    stable.reverse()
    pad=[parse(s) for s in stderr_text.splitlines() if s.startswith('EDEN_PAD_HEARTBEAT')]
    result={
        'source_sha':sha.group(1) if sha else None,
        'windows':len(groups['frame']),
        'total_displayed_frames':groups['gpu'][-1]['frame'],
        'mean_fps':round(statistics.mean(v['fps'] for v in groups['frame']),3),
        'late50_frames':sum(v['late50'] for v in groups['frame']),
        'max_frame_ms':max(v['worst_ms'] for v in groups['frame']),
        'gpu_queue_full':groups['gpu'][-1]['full_calls'],
        'early_chunk_dispatches':groups['early'][-1]['dispatched'] if groups['early'] else None,
        'cpu_last_epoch':core_epochs,
        'stable_workload_last_seconds_approx':len(stable)*5,
        'stable_workload_first_frame':stable[0]['frame'] if stable else None,
        'stable_workload_last_frame':stable[-1]['frame'] if stable else None,
        'stable_per_frame':{k:round(v,2) for k,v in reference.items()} if stable else None,
        'stable_early_dispatches_per_frame':round(statistics.mean(row['early'] for row in stable),2)
              if stable and all('early' in row for row in stable) else None,
        'potential_repetition':len(stable)>=12,
        'controller_last':pad[-1] if pad else None,
        'limitations':'Identical workload counters do not establish identical pixels, progression of guest game state, deadlock or user input delivery.',
    }
    return result

def self_test():
    def text(count,stable):
        lines=['EDEN_BUILD_SOURCE source_sha='+'f'*40]
        for i in range(count):
            n=i+1
            # Zero late50 and 30FPS only in steady tail; varying drawn/writes
            # elsewhere, even when 30FPS remains stable.
            draw=n*44100 if stable else n*n*100
            writes=n*66560 if stable else n*n*230
            ipc=n*7300 if stable else n*n*80
            lines.extend([
                f'EDEN_VULKAN_FRAME frames=150 seconds=5 fps=30 worst_ms=33 late50=0',
                f'EDEN_DEV_GPU frame={n*150} draws={draw} full_calls=0',
                f'EDEN_DEV_GUEST cpu_write_calls={writes} ipc_calls={ipc}',
                f'EDEN_SCHEDULER_PREFLIGHT frame={n*150} dispatched={n*2700}',
            ])
        return '\n'.join(lines)
    positive=analyze(text(25,True))
    assert positive['potential_repetition'] and positive['stable_workload_last_seconds_approx']==120
    negative=analyze(text(25,False))
    assert not negative['potential_repetition']
    assert negative['stable_workload_last_seconds_approx']<=5
    assert positive['early_chunk_dispatches']==67500
    assert positive['gpu_queue_full']==0
    print('R386 offline freeze signature self-test PASS (repeated/variable workloads, not GPU-stop oracle)')

if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        self_test()
    elif len(sys.argv) in (2,3):
        heap=Path(sys.argv[1]).read_text(errors='replace')
        stderr=Path(sys.argv[2]).read_text(errors='replace') if len(sys.argv)==3 else ''
        print(json.dumps(analyze(heap,stderr),indent=2,ensure_ascii=False))
    else:
        raise SystemExit(__doc__)
