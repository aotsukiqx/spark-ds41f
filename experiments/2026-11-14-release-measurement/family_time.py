#!/usr/bin/env python3
"""Kernel time by family in one torch-profiler trace (row sums, not the union).

usage: family_time.py TRACE.json.gz [--steps N] [--top 15]

For prefill the union is less interesting than the split: a chunk's time is
bandwidth in some kernels and Tensor Core work in others, and the levers are
different in each. Prints ms per step (or per window) by kernel name.
"""
import argparse
import gzip
import json
from collections import defaultdict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace")
    parser.add_argument("--steps", type=float, default=None)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    opener = gzip.open if args.trace.endswith(".gz") else open
    with opener(args.trace, "rt", encoding="utf-8") as handle:
        events = json.load(handle)["traceEvents"]
    per: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    for event in events:
        if event.get("ph") != "X" or event.get("cat") != "kernel":
            continue
        name = event.get("name", "?")
        per[name] += event.get("dur", 0) / 1000.0
        count[name] += 1
    total = sum(per.values())
    steps = args.steps or 1.0
    print(f"total {total:.1f} ms over {sum(count.values())} kernels"
          + (f", {steps:g} steps" if args.steps else ""))
    for name, ms in sorted(per.items(), key=lambda item: -item[1])[: args.top]:
        print(f"  {ms / steps:9.2f}  {count[name] / steps:8.1f}  {name[:78]}")


if __name__ == "__main__":
    main()
