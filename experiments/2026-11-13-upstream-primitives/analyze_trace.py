#!/usr/bin/env python3
"""Where a decode step's wall time goes, from one rank's torch profiler trace.

usage: analyze_trace.py TRACE.json.gz [--steps N] [--min-ms 0.05] [--top 12]

Kernels are merged into their union (overlapping launches on different streams
count once) and measured against the trace window itself, not against a
client-side wall time: the profiler brackets the server, so its window can
include a step before the first request and one after the last. The idle share
is the latency-bound bucket — everything the GPU spent not executing kernels.
The largest gaps are attributed to the kernel that ran last before each gap.
"""
import argparse
import gzip
import json
from collections import Counter, defaultdict


def kernel_intervals(path: str) -> list[tuple[float, float, str]]:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        events = json.load(handle)["traceEvents"]
    out = []
    for event in events:
        if event.get("ph") != "X" or event.get("cat") != "kernel":
            continue
        dur = event.get("dur")
        if not dur:
            continue
        out.append((event["ts"], event["ts"] + dur, event.get("name", "?")))
    out.sort()
    return out


def union_us(intervals: list[tuple[float, float, str]]) -> float:
    total, start, end = 0.0, None, None
    for begin, finish, _ in intervals:
        if start is None:
            start, end = begin, finish
        elif begin > end:
            total += end - start
            start, end = begin, finish
        else:
            end = max(end, finish)
    if start is not None:
        total += end - start
    return total


def gaps(intervals: list[tuple[float, float, str]], min_us: float) -> dict[str, tuple[int, float]]:
    per: dict[str, list[float]] = defaultdict(list)
    end, last = None, "?"
    for begin, finish, name in intervals:
        if end is not None and begin - end >= min_us:
            per[last].append(begin - end)
        if end is None or finish > end:
            end, last = finish, name
    return {name: (len(vs), sum(vs)) for name, vs in per.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace")
    parser.add_argument("--steps", type=float, default=None)
    parser.add_argument("--min-ms", type=float, default=0.05)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--count", type=int, default=8, help="most frequent kernels to print")
    args = parser.parse_args()
    intervals = kernel_intervals(args.trace)
    start = intervals[0][0]
    end = max(finish for _, finish, _ in intervals)
    window_ms = (end - start) / 1000.0
    busy_ms = union_us(intervals) / 1000.0
    steps = args.steps
    report = {
        "kernels": len(intervals),
        "window_ms": round(window_ms, 1),
        "gpu_busy_ms": round(busy_ms, 1),
        "idle_ms": round(window_ms - busy_ms, 1),
        "idle_share": round((window_ms - busy_ms) / window_ms, 4),
    }
    if steps:
        report.update({
            "steps": steps,
            "window_per_step_ms": round(window_ms / steps, 2),
            "busy_per_step_ms": round(busy_ms / steps, 2),
            "idle_per_step_ms": round((window_ms - busy_ms) / steps, 2),
        })
    print(json.dumps(report))

    counts = Counter(name for _, _, name in intervals)
    print("kernels per step (window / steps):")
    for name, count in counts.most_common(args.count):
        per = f"{count / steps:8.1f}" if steps else f"{count:8d}"
        print(f"  {per}  {name[:88]}")

    per_gap = gaps(intervals, args.min_ms * 1000)
    rows = sorted(per_gap.items(), key=lambda item: -item[1][1])[: args.top]
    print(f"{'idle ms':>10}  {'gaps':>6}  kernel before the gap")
    for name, (count, us) in rows:
        print(f"{us / 1000:10.3f}  {count:6d}  {name[:88]}")


if __name__ == "__main__":
    main()
