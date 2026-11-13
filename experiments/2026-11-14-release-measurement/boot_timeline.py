#!/usr/bin/env python3
"""Boot timeline from a `cluster start --apply` log.

usage: boot_timeline.py LOG

The launcher prints cumulative offsets like "(+118.0s)"; this script keeps the
offset-bearing lines and prints the deltas between them, so the cost of each
phase (image pull, weight load, kernel preparation, graph capture, readiness)
is visible without a profiler.
"""
import re
import sys

OFFSET = re.compile(r"\(\+([0-9.]+)s\)")


def main() -> None:
    path = sys.argv[1]
    entries = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = OFFSET.search(line)
            if match:
                entries.append((float(match.group(1)), line.strip()))
    entries.sort()
    previous = 0.0
    for offset, line in entries:
        text = OFFSET.sub("", line).strip(" :")
        print(f"+{offset:8.1f}s  (+{offset - previous:6.1f}s)  {text[:120]}")
        previous = offset


if __name__ == "__main__":
    main()
