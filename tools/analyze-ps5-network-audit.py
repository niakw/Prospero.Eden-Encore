#!/usr/bin/env python3
"""Read-only Encore network-accepted.log analyzer (launcher, guest, native).

Never reconfigures DNS; never performs network lookups. Counts successful API
calls/bytes, not on-the-wire packets, and does not infer IP->domain ownership.

Usage:
  python3 tools/analyze-ps5-network-audit.py logs/network-accepted.log*
  python3 tools/analyze-ps5-network-audit.py --self-test
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import tempfile

# Old firmware captures carried epoch seconds only. The new audit format
# supplies explicit UTC milliseconds and a monotonic time in nanoseconds.
# Both remain optional for read-only, backwards-compatible analysis.
LINE = re.compile(
    r"^epoch=(?P<epoch>\d+)"
    r"(?: utc=(?P<utc>\S+) mono_ns=(?P<mono_ns>-?\d+))?"
    r" scope=(?P<scope>launcher|guest|native)"
    r" event=(?P<event>[a-z][a-z-]*) target=(?P<target>\S{1,256}) "
    r"bytes=(?P<bytes>\d+) status=(?P<status>-?\d+)"
    r"(?: count=(?P<count>\d+))?$"
)
LEGACY_SUMMARY = re.compile(
    r"^epoch=(?P<epoch>\d+) scope=guest "
    r"event=dns-denied-summary target=aggregated count=(?P<count>\d+)$"
)
IPV4_PORT = re.compile(
    r"^(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}$"
)
DNS_EVENTS = {"dns-allowed", "dns-denied", "dns-resolved", "dns-error"}
SOCKET_EVENTS = {"connect", "tx", "rx", "numeric-ip"}


def summarize(paths: list[Path]) -> dict:
    by_event: Counter[tuple[str, str]] = Counter()
    dns: dict[str, Counter[str]] = defaultdict(Counter)
    dns_scoped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    connections: Counter[tuple[str, str]] = Counter()
    io: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    malformed = 0
    observed = 0
    latest_epoch = None
    earliest_epoch = None
    utc_rows = 0
    legacy_rows = 0
    summarized_dns_denials = 0
    mono_start = None
    mono_end = None
    for path in paths:
        with path.open(encoding="utf-8", errors="replace") as f:
            for row in f:
                line = row.rstrip("\r\n")
                match = LINE.fullmatch(line)
                legacy_summary = LEGACY_SUMMARY.fullmatch(line) if not match else None
                if not match and not legacy_summary:
                    malformed += 1
                    continue
                if legacy_summary:
                    rec = legacy_summary.groupdict()
                    scope, event, target, num_bytes, status = (
                        "guest", "dns-denied-summary", "aggregated", "0", "0")
                    timestamp = int(rec["epoch"])
                    summarized_dns_denials += int(rec["count"])
                    legacy_rows += 1
                else:
                    rec = match.groupdict()
                    scope, event, target = rec["scope"], rec["event"], rec["target"]
                    num_bytes, status = rec["bytes"], rec["status"]
                    timestamp = int(rec["epoch"])
                    if event == "dns-denied-summary":
                        summarized_dns_denials += int(rec["count"] or 0)
                    if rec["utc"] is not None:
                        try:
                            wall = datetime.fromisoformat(rec["utc"].replace("Z", "+00:00"))
                            if (not rec["utc"].endswith("Z") or
                                int(wall.timestamp()) != timestamp):
                                raise ValueError("UTC and epoch differ")
                        except (ValueError, OverflowError):
                            malformed += 1
                            continue
                        utc_rows += 1
                        monotonic = int(rec["mono_ns"])
                        if monotonic >= 0:
                            mono_start = monotonic if mono_start is None else min(mono_start, monotonic)
                            mono_end = monotonic if mono_end is None else max(mono_end, monotonic)
                    else:
                        legacy_rows += 1
                earliest_epoch = timestamp if earliest_epoch is None else min(earliest_epoch, timestamp)
                latest_epoch = timestamp if latest_epoch is None else max(latest_epoch, timestamp)
                observed += 1
                by_event[(scope, event)] += 1
                if event in DNS_EVENTS:
                    dns[event][target.lower().rstrip(".")] += 1
                    dns_scoped[(scope, event)][target.lower().rstrip(".")] += 1
                elif event in SOCKET_EVENTS:
                    if event == "connect":
                        connections[(scope, target)] += 1
                    if event in ("tx", "rx"):
                        io[(scope, target)][event] += int(num_bytes)
                        io[(scope, target)][event + "_calls"] += 1
    return {
        "events": observed,
        "invalid_lines": malformed,
        "start": earliest_epoch,
        "end": latest_epoch,
        "utc_rows": utc_rows,
        "legacy_rows": legacy_rows,
        "monotonic_ns_range": (mono_start, mono_end),
        "summarized_dns_denials": summarized_dns_denials,
        "by_event": by_event,
        "dns": dns,
        "dns_scoped": dns_scoped,
        "connect": connections,
        "io": io,
    }


def display(report: dict, top: int) -> str:
    def utc_at(epoch: int | None) -> str:
        return (datetime.fromtimestamp(epoch, timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ")) if epoch is not None else "unknown"

    lines = [
        f"Events: {report['events']:,}; malformed lines: {report['invalid_lines']:,}; "
        f"UTC: {utc_at(report['start'])} – {utc_at(report['end'])} "
        f"(epoch {report['start']}–{report['end']})",
        f"Timestamp coverage: {report['utc_rows']:,} with UTC+monotonic, "
        f"{report['legacy_rows']:,} legacy epoch-only; "
        f"aggregated denied DNS attempts: {report['summarized_dns_denials']:,} "
        f"(summary flush time, not individual-request timestamps)",
        "",
        "Events by layer (guest HLE and native socket calls can refer to the SAME traffic):",
    ]
    for (scope, event), count in report["by_event"].most_common():
        lines.append(f"  {scope:8} {event:16} {count:>9,}")
    for scope, kind, label in (
        ("guest", "dns-denied", "Guest domain lookups denied by Eden"),
        ("launcher", "dns-denied", "Launcher domain lookups denied by Eden"),
        ("guest", "dns-allowed", "Guest domains allowed by Eden (NOT proof of DNS success)"),
        ("guest", "dns-resolved", "Guest resolver succeeded after Eden allowed the name"),
        ("guest", "dns-error", "Guest resolver failed after Eden allowed the name"),
        ("launcher", "dns-resolved", "Launcher resolver succeeded"),
        ("launcher", "dns-error", "Launcher resolver failed"),
    ):
        lines.extend(("", label + ":"))
        ranking = report["dns_scoped"][(scope, kind)].most_common(top)
        lines.extend(f"  {count:>7,}  {host}" for host, count in ranking)
        if not ranking:
            lines.append("  (none observed)")
    lines.extend(("", "Socket connects observed by Eden's API boundaries:"))
    for (scope, target), count in report["connect"].most_common(top):
        lines.append(f"  {count:>7,}  {scope:8} {target}")
    if not report["connect"]:
        lines.append("  (none observed)")
    lines.extend(("", "Socket API bytes (not wire packets, duplicate layers possible):"))
    ranking = sorted(
        report["io"].items(),
        key=lambda item: item[1]["tx"] + item[1]["rx"],
        reverse=True,
    )[:top]
    for (scope, target), values in ranking:
        lines.append(
            f"  {scope:8} {target:32} "
            f"tx={values['tx']:,} ({values['tx_calls']} calls) "
            f"rx={values['rx']:,} ({values['rx_calls']} calls)"
        )
    if not ranking:
        lines.append("  (none observed)")
    direct = [
        (scope, host, count)
        for (scope, host), count in report["connect"].items()
        if IPV4_PORT.fullmatch(host)
    ]
    if direct:
        lines.extend(("", "Direct-IP destinations (cannot infer operator or bypass from IP alone):"))
        for scope, host, count in sorted(direct, key=lambda x: -x[2])[:top]:
            lines.append(f"  {count:>7,}  {scope:8} {host}")
    lines.extend((
        "",
        "NOTE: Eden domain matches precede ordinary DNS. NanoDNS/router DNS may",
        "still block an Eden-allowed lookup. DNS permission is not Internet access.",
        "NOTE: The logger observes selected API boundaries, not every PS5 packet.",
        "No domains are inferred from socket IPs; external DNS logs are needed",
        "to establish whether a direct-IP destination belongs to a publisher.",
    ))
    return "\n".join(lines)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="eden-network-audit-report-") as tmp:
        path = Path(tmp) / "network-accepted.log"
        path.write_text("\n".join((
            "epoch=10 scope=guest event=dns-allowed target=allowed.example bytes=0 status=0",
            "epoch=11 scope=guest event=dns-denied target=API.EA.COM bytes=0 status=1",
            "epoch=12 scope=launcher event=dns-resolved target=api.nlib.cc bytes=0 status=0",
            "epoch=13 scope=guest event=connect target=203.0.113.10:443 bytes=0 status=0",
            "epoch=14 scope=guest event=tx target=fd:12 bytes=500 status=0",
            "epoch=15 scope=native event=tx target=203.0.113.10:443 bytes=500 status=0",
            "epoch=16 scope=guest event=rx target=fd:12 bytes=20 status=0",
            "epoch=17 scope=guest event=dns-error target=fail.example bytes=0 status=1",
            "epoch=18 scope=guest event=dns-resolved target=pass.example bytes=0 status=0",
            "not-a-valid-row",
        )) + "\n")
        report = summarize([path])
        assert report["events"] == 9 and report["invalid_lines"] == 1
        assert report["legacy_rows"] == 9 and report["utc_rows"] == 0
        assert "UTC: 1970-01-01T00:00:10Z" in display(report, 10)
        # Real historical captures have a summary without bytes/status;
        # it is a valid event, not a malformed line to discard.
        with path.open("a") as old:
            old.write("epoch=20 scope=guest event=dns-denied-summary target=aggregated count=42\n")
        old_result = summarize([path])
        assert old_result["invalid_lines"] == 1 and old_result["events"] == 10
        assert old_result["summarized_dns_denials"] == 42
        # Validate wall/monotonic time, new summaries and guard against a
        # future mismatch between UTC and epoch clocks.
        with path.open("a") as new:
            new.write("epoch=1791977112 utc=2026-10-14T11:25:12.125Z mono_ns=123450000000 scope=guest event=dns-denied target=api.example bytes=0 status=1\n")
            new.write("epoch=1791977112 utc=2026-10-14T11:25:12.126Z mono_ns=123450001000 scope=guest event=dns-denied-summary target=aggregated bytes=0 status=0 count=3\n")
            new.write("epoch=1791977112 utc=2026-10-14T11:25:13.000Z mono_ns=123450003000 scope=guest event=dns-denied target=bad.example bytes=0 status=1\n")
        new_result = summarize([path])
        assert new_result["utc_rows"] == 2 and new_result["invalid_lines"] == 2
        assert new_result["summarized_dns_denials"] == 45
        assert new_result["monotonic_ns_range"] == (123450000000, 123450001000)
        assert "2026-10-14T11:25:12Z" in display(new_result, 10)
        assert report["dns_scoped"][("guest", "dns-resolved")]["pass.example"] == 1
        assert report["dns_scoped"][("launcher", "dns-resolved")]["api.nlib.cc"] == 1
        assert report["dns_scoped"][("guest", "dns-error")]["fail.example"] == 1
        assert report["dns"]["dns-denied"]["api.ea.com"] == 1
        assert report["dns"]["dns-allowed"]["allowed.example"] == 1
        assert report["io"][("guest", "fd:12")]["tx"] == 500
        assert report["io"][("native", "203.0.113.10:443")]["tx"] == 500
        assert "duplicate layers possible" in display(report, 10)
        assert "Eden-allowed lookup" in display(report, 10)
    print("NETWORK_AUDIT_ANALYSIS_PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="*",
                        help="network-accepted.log or network-accepted.log.prev")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.logs:
        parser.error("provide at least one network-accepted.log file")
    if not 1 <= args.top <= 100:
        parser.error("--top must be between 1 and 100")
    for log in args.logs:
        if not log.is_file():
            parser.error(f"not a file: {log}")
    print(display(summarize(args.logs), args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
