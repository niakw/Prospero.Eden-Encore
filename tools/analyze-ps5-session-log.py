#!/usr/bin/env python3
"""Offline, read-only correlation of Encore stderr and heap log snapshots.

No console access, native build, or game files required. Frames presented,
input callbacks and successful teardown do NOT prove guest game progress.
"""
import argparse
import json
import re
from pathlib import Path

FIELDS = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")


def fields(line):
    return dict(FIELDS.findall(line))


def replay(stderr, heap):
    sessions = []
    session = {"pads": [], "chains": [], "lifo": []}
    for line in stderr.splitlines():
        if line.startswith("EDEN_PAD_INPUT mode=") and any(session.values()):
            sessions.append(session)
            session = {"pads": [], "chains": [], "lifo": []}
        if line.startswith("EDEN_PAD_HEARTBEAT "):
            session["pads"].append(fields(line))
        elif line.startswith("EDEN_PAD_INPUT_CHAIN "):
            session["chains"].append(fields(line))
        elif line.startswith("EDEN_NPAD_PLUS_LIFO "):
            session["lifo"].append(fields(line))
    if any(session.values()):
        sessions.append(session)

    # 'connected' on a heartbeat is an open-slot bitmap, NOT raw
    # Data.connected. Do not compare monotonically reset counters across
    # distinct launches in the same app process.
    stalls = []
    for number, session in enumerate(sessions, start=1):
        streak, streaks = [], []
        for before, after in zip(session['pads'], session['pads'][1:]):
            quiet = (int(after['samples']) > int(before['samples']) and
                     after['usable'] == before['usable'] and
                     after['intercepted'] == before['intercepted'] and
                     after['errors'] == before['errors'])
            if quiet:
                streak.append((before, after))
            elif streak:
                streaks.append(streak)
                streak = []
        if streak:
            streaks.append(streak)
        stalls.extend({
            "session": number,
            "first_poll": int(s[0][0]['polls']),
            "last_poll": int(s[-1][1]['polls']),
            "duration_ms": int(s[-1][1]['epoch_ms']) - int(s[0][0]['epoch_ms']),
            "samples_added": int(s[-1][1]['samples']) - int(s[0][0]['samples']),
            "usable_added": 0,
            "reason": "unusable samples; not proof of guest freeze",
        } for s in streaks)

    frames = []
    pressures = []
    for line in heap.splitlines():
        if line.startswith('EDEN_VULKAN_FRAME '):
            frames.append(fields(line))
        elif line.startswith('EDEN_FRAME_PRESSURE '):
            pressures.append(fields(line))
    report = {
        "input": {
            "heartbeats": sum(len(s['pads']) for s in sessions),
            "session_count": len(sessions), "unusable_streaks": stalls,
            "plus_published": sum(int(s['chains'][-1]['published_plus_edges'])
                                  for s in sessions if s['chains']),
            "plus_seen_in_npad": sum(int(s['lifo'][-1]['edges'])
                                    for s in sessions if s['lifo']),
            "npad_plus_is_guest_consumption_proof": False,
        },
        "graphics": {
            "windows": len(frames),
            "windows_below_20_fps": sum(float(f['fps']) < 20 for f in frames),
            "windows_with_worst_frame_over_400ms": sum(float(f['worst_ms']) > 400 for f in frames),
            "windows_near_30fps": sum(29.95 <= float(f['fps']) <= 30.05 for f in frames),
            "last_five_mean_reported_gpu_idle_ms":
                round(sum(float(p['gpu_idle_ms']) for p in pressures[-5:]) / 5, 1)
                if len(pressures) >= 5 else None,
            "frame_presentation_proves_guest_progress": False,
        },
        "limitations": [
            "Only original source logs and code can establish sample connected/intercept reason.",
            "Counter changes do not show video-content freshness or guest-thread wait ownership.",
            "A source or CI pass cannot establish a console performance or stability improvement.",
        ],
    }
    return report


def self_test():
    h = lambda poll, sam, use, ms: (f'EDEN_PAD_HEARTBEAT polls={poll} samples={sam} '
        f'usable={use} intercepted=0 errors=0 connected=1 epoch_ms={ms}')
    s = '\n'.join([h(1250, 3000, 3000, 0), h(2500, 4250, 3000, 5000),
                   h(3750, 5500, 3000, 10000), h(5000, 6100, 3600, 15000),
                   'EDEN_PAD_INPUT_CHAIN published_plus_edges=2',
                   'EDEN_NPAD_PLUS_LIFO edges=2'])
    g = '\n'.join(['EDEN_VULKAN_FRAME fps=18.5 worst_ms=450',
                   'EDEN_FRAME_PRESSURE gpu_idle_ms=4000'] * 5)
    a = replay(s, g)
    assert a['input']['unusable_streaks'][0]['duration_ms'] == 10000
    assert a['input']['unusable_streaks'][0]['samples_added'] == 2500
    assert a['input']['plus_published'] == a['input']['plus_seen_in_npad'] == 2
    assert a['graphics']['windows'] == a['graphics']['windows_below_20_fps'] == 5
    assert a['graphics']['last_five_mean_reported_gpu_idle_ms'] == 4000.0
    assert not a['graphics']['frame_presentation_proves_guest_progress']
    two = replay(s + '\nEDEN_PAD_INPUT mode=dualsense\n' +
                 h(1250, 100, 100, 21000) + '\n' +
                 'EDEN_PAD_INPUT_CHAIN published_plus_edges=0', g)
    assert two['input']['session_count'] == 2
    assert two['input']['plus_published'] == 2
    assert two['input']['plus_seen_in_npad'] == 2
    assert len(two['input']['unusable_streaks']) == 1
    print('PASS: offline pad/graphics correlation and multi-session reset')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stderr', type=Path)
    ap.add_argument('--heap', type=Path)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        self_test()
    else:
        if not a.stderr or not a.heap:
            ap.error('--stderr and --heap required unless --self-test')
        print(json.dumps(replay(a.stderr.read_text(errors='replace'),
                                a.heap.read_text(errors='replace')),
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
