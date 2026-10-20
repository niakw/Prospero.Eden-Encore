#!/usr/bin/env python3
"""Source-extracted selected native spans after physical unmap/remap."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-B', str(root / 'tools/check-native-device-span-bounds-host.py'),
                '--continuity'], check=True)
