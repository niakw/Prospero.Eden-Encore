#!/usr/bin/env python3
"""Source contract for bounded native PS5 stdout/stderr log storage.

This does not start a logfile thread or run a native PS5 build; the future
native/host test pass must still exercise descriptor failures separately.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pipe = (root / "headless/log_pipe.h").read_text()
main = (root / "headless/main.cpp").read_text()

assert "segment_limit = 8u * 1024u * 1024u" in pipe
assert "kReleaseLogSegmentBytes = 8u * 1024u * 1024u" in main
assert 'Eden::LogFile("stderr.first.log")' in main
assert 'Eden::LogFile("heap.first.log")' in main
assert "stdout_pipe.Attach(" in main and "stderr_pipe.Attach(" in main
attach = pipe.split("bool Attach(", 1)[1].split("void Detach()", 1)[0]
assert "worker = std::thread([this] { Drain(); });" in attach
assert "catch (...)" in attach
assert "(void)dup2(file_fd, stream_fd);" in attach
assert "close(read_fd);" in attach and "close(file_fd);" in attach
assert "stream = nullptr;" in attach
assert "return false;" in attach

rotate = pipe.split("bool Rotate()", 1)[1].split("void Drain()", 1)[0]
assert "if (!rotated)" in rotate and "rotated = true;" in rotate
assert "std::rename(log_path.c_str(), first_log_path.c_str())" in rotate
assert 'open(log_path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666)' in rotate
assert "ftruncate(" not in rotate and "lseek(" not in rotate
assert "bytes = 0;" in rotate
assert "[Eden Encore] log segment rotated" in rotate

drain = pipe.split("void Drain()", 1)[1].split("std::FILE* stream", 1)[0]
assert "bytes + static_cast<std::size_t>(count) > limit" in drain
assert "if (errno == EINTR) continue;" in drain
assert "std::scoped_lock lock{file_mutex};" in drain
assert "bytes += static_cast<std::size_t>(result);" in drain
assert "continue;" in drain  # discard chunk on failed rotation; never fill SSD

print("PASS source: native 8MiB double segments, recoverable thread failure, bounded recycle")
print("PS5 SDK compile / descriptor fault-injection / hardware execution: NOT TESTED")
