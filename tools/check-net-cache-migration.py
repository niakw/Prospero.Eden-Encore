#!/usr/bin/env python3
"""Regression: upgrading a restored Eden HTTP patch must not invalidate whole cache."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
migrator = root / "tools/migrate-net-user-agent-cache.py"
script = (root / "tools/apply-eden-backports.sh").read_text()
assert "7117c1c3f353157b7fa46a86c6f77226b1183d9b374462cefe8b8dc5f32bf613" in script
assert "python3 -B \"$root/tools/migrate-net-user-agent-cache.py\" \"$eden\"" in script

old = '''        httplib::Request request{ .method = "GET", .path = path };
        request.headers.emplace("User-Agent", "Prospero.Eden-Encore/1");
        request.headers.emplace("Accept", "*/*");
        if (!result) {
            LOG_ERROR(Common, "GET to {}{} returned null", url, path);
            return {};
        }
'''
for case in ("legacy-cache", "partially-upgraded", "unpatched-source", "unexpected-error"):
    with tempfile.TemporaryDirectory(prefix="encore-net-migrate-") as tmp:
        source = Path(tmp) / "src/common/net/net.cpp"
        source.parent.mkdir(parents=True)
        initial = old
        if case == "partially-upgraded":
            initial = initial.replace(
                '            LOG_ERROR(Common, "GET to {}{} returned null", url, path);',
                '            LOG_ERROR(Common, "GET to {}{} returned null: {}", url, path,\n'
                '                      httplib::to_string(result.error()));',
            )
        elif case == "unpatched-source":
            initial = initial.replace('        request.headers.emplace("Accept", "*/*");\n', '')
        elif case == "unexpected-error":
            initial = initial.replace('returned null", url', 'other message", url')
        source.write_text(initial)
        result = subprocess.run([sys.executable, "-B", str(migrator), tmp],
                                capture_output=True, text=True)
        successful = case in ("legacy-cache", "partially-upgraded")
        assert (result.returncode == 0) == successful, (case, result.stdout, result.stderr)
        if successful:
            upgraded = source.read_text()
            assert upgraded.count('httplib::to_string(result.error())') == 1, case
            again = subprocess.run([sys.executable, "-B", str(migrator), tmp],
                                   capture_output=True, text=True)
            assert again.returncode == 0 and source.read_text() == upgraded
        else:
            assert source.read_text() == initial, "migration modified an unrecognized source"
print("Cached Eden network-backport migration: four guarded scenarios PASS")
