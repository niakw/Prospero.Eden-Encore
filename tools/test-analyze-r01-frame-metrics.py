#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic, test-only telemetry; never claimed as measured FC27 performance."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("analyze-r01-frame-metrics.py")
spec = importlib.util.spec_from_file_location("r01_metrics_analyzer", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

def row(frame, source, real, generated, presented, interval=1000000000):
    return (f"EDEN_R01_FRAME_METRICS frame={frame} interval_ns={interval} "
            f"source_composites={source} real_queued={real} generated_queued={generated} "
            f"source_skipped=0 loading_queued=0 present_returned={presented} "
            f"source_callback_fps={source}.000 real_queue_fps={real}.000 "
            f"generated_queue_fps={generated}.000 present_return_fps={presented}.000 "
            f"scope={module.SCOPE}")

class R01MetricsTests(unittest.TestCase):
    def test_30_to_60_is_not_guest_fps(self):
        rows, bad = module.parse_logs([row(30, 30, 30, 30, 60)])
        report=module.summary(rows,bad)
        self.assertEqual(report["sessions"][0]["rates"],
            {"source_callback_fps": 30.0, "real_queued_fps": 30.0,
             "generated_queued_fps": 30.0, "present_return_fps": 60.0})
        self.assertIsNone(report["actual_guest_fps"])
        self.assertIsNone(report["input_to_photon_latency"])
        self.assertIsNone(report["gpu_render_time_ms"])
    def test_weighted_windows_not_mean_fps(self):
        a=row(10, 10, 10, 0, 10, 1000000000)
        b=row(50, 10, 10, 0, 10, 3000000000)
        report=module.summary(*module.parse_logs([a,b]))
        self.assertEqual(report["sessions"][0]["rates"]["real_queued_fps"],5.0)
        self.assertEqual(report["sessions"][0]["duration_ns"],4000000000)
    def test_session_reset_and_malformed(self):
        logs=[row(100, 1, 1, 0, 1), row(20, 2, 2, 0, 2),
              row(25, 3, 3, 0, 3).replace("scope="+module.SCOPE,"scope=fabricated_guest_fps"),
              "EDEN_R01_FRAME_METRICS broken"]
        report=module.summary(*module.parse_logs(logs))
        self.assertEqual(len(report["sessions"]),2)
        self.assertEqual(report["sessions"][1]["counts"]["real_queued"],2)
        self.assertEqual(len(report["rejected_lines"]),2)
    def test_cli_json_and_absence(self):
        with tempfile.TemporaryDirectory() as folder:
            log=Path(folder)/"boot.log"
            log.write_text("foo\n"+row(30,30,30,30,60)+"\n")
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(module.main(["--json",str(log)]),0)
            self.assertEqual(json.loads(out.getvalue())["sessions"][0]["counts"]["present_returned"],60)
            log.write_text("unrelated logs")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main([str(log)]),2)

if __name__ == "__main__":
    unittest.main()
