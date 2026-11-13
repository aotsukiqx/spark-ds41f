#!/usr/bin/env python3
"""Prefix-cache retention probe: hit rates at block boundaries and under eviction.

usage: measure_cache.py BASE_URL [--prefix-tokens 65000] [--distinct 200] [--reuse 8]

Builds one long prefix, then:
1. asks for it ``--reuse`` times and reports each request's cached-token count
   (the second and later requests should be served almost entirely from the
   prefix cache);
2. asks for ``--distinct`` different suffixes under the same prefix, which is
   what agent traffic looks like, and reports the cached count each time;
3. asks for ``--distinct`` *unrelated* long prompts to pressure the pool, then
   re-asks for the original prefix and reports whether it survived eviction.

The counters come from the API's usage block (``prompt_tokens_details.cached_tokens``)
when the server reports them; otherwise the metric deltas are printed instead.
"""
import argparse
import json
import re
import urllib.request

FILLER = ("The quick brown fox jumps over the lazy dog while the lighthouse keeper records the "
          "tide, the wind, and the state of every lamp for the morning report. ")


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=120) as response:
        return json.loads(response.read())


def post(base: str, path: str, body: dict) -> dict:
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.loads(response.read())


def metrics(base: str) -> dict[str, float]:
    with urllib.request.urlopen(base + "/metrics", timeout=120) as response:
        text = response.read().decode()
    out = {}
    for name in ("vllm:prefix_cache_hits_total", "vllm:prefix_cache_queries_total"):
        values = [float(m) for m in re.findall(rf"^{re.escape(name)}{{[^}}]*}} ([0-9.e+]+)$", text, re.M)]
        out[name] = sum(values)
    return out


def ask(base: str, model: str, prompt: str, limit: int = 2) -> dict:
    body = post(base, "/v1/completions", {"model": model, "prompt": prompt,
                                          "max_tokens": limit, "temperature": 0,
                                          "ignore_eos": True})
    usage = body.get("usage", {})
    details = usage.get("prompt_tokens_details") or {}
    return {"prompt_tokens": usage.get("prompt_tokens"),
            "cached_tokens": details.get("cached_tokens")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("--prefix-tokens", type=int, default=65_000)
    parser.add_argument("--distinct", type=int, default=200)
    parser.add_argument("--reuse", type=int, default=8)
    parser.add_argument("--pressure-only", action="store_true",
                        help="skip the reuse phases and pressure the pool with unrelated prefixes")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    model = get(base, "/v1/models")["data"][0]["id"]

    unit = FILLER
    unit_count = int(post(base, "/tokenize", {"model": model, "prompt": unit})["count"])
    prefix = unit * max(1, args.prefix_tokens // unit_count)
    prefix_count = int(post(base, "/tokenize", {"model": model, "prompt": prefix})["count"])
    print(json.dumps({"prefix_tokens": prefix_count}), flush=True)

    rows = []
    for i in range(0 if args.pressure_only else args.reuse):
        row = ask(base, model, prefix + f"\n\nRound {i}: summarize the tide records.")
        row["phase"] = "reuse"
        rows.append(row)
        print(json.dumps(row), flush=True)

    for i in range(0 if args.pressure_only else args.reuse):
        row = ask(base, model, prefix + f"\n\nCase {i}: name the failure mode number {i}.")
        row["phase"] = "shared-prefix"
        rows.append(row)
        print(json.dumps(row), flush=True)

    if args.pressure_only:
        ask(base, model, prefix + "\n\nRound 0 again: summarize the tide records.", 1)
        print(json.dumps({"phase": "survived-before-pressure"}), flush=True)
    before = metrics(base)
    for i in range(args.distinct):
        # A unique leading identifier so the pressure prompts share no prefix:
        # the pool must hold them, or the original prefix is what gets evicted.
        ask(base, model, f"Pressure set {i} identifier {i * 7919}. "
                         + unit * max(1, args.prefix_tokens // unit_count), 1)
    after = metrics(base)
    survivor = ask(base, model, prefix + "\n\nRound 0 again: summarize the tide records.")
    survivor["phase"] = "after-eviction-pressure"
    print(json.dumps(survivor), flush=True)

    queries = after["vllm:prefix_cache_queries_total"] - before["vllm:prefix_cache_queries_total"]
    hits = after["vllm:prefix_cache_hits_total"] - before["vllm:prefix_cache_hits_total"]
    print(json.dumps({"phase": "pressure", "distinct": args.distinct,
                      "queries": queries, "hits": hits,
                      "hit_rate": round(hits / queries, 4) if queries else None}), flush=True)


if __name__ == "__main__":
    main()
