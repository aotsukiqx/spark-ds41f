#!/usr/bin/env python3
"""One profiled decode round against a profiler-enabled arm.

usage: profile_drive.py BASE_URL --streams N [--tokens N] [--case code|prose]

Runs a warm-up round, wraps one round of N concurrent identical requests in
/start_profile and /stop_profile, and prints one JSON line: the round's wall
time, completion tokens, decode steps (from the draft counter), step time,
tokens/s, and the profiler directory the server wrote to. The prompts are fixed
so the round decodes the same text every time.
"""
import argparse
import json
import re
import threading
import time
import urllib.request

PROMPTS = {
    "code": "Write a complete Python implementation of an LRU cache using only the standard "
            "library. Include type hints, O(1) get and put methods, capacity validation, and a "
            "short executable example. Explain the complexity after the code.",
    "prose": "Write a paragraph about the history of the lighthouse.",
}
COUNTERS = ("vllm:spec_decode_num_drafts_total", "vllm:generation_tokens_total")


def counters(base: str) -> dict[str, float]:
    with urllib.request.urlopen(base + "/metrics", timeout=60) as response:
        text = response.read().decode()
    out = {}
    for name in COUNTERS:
        out[name] = sum(float(m) for m in re.findall(rf"^{re.escape(name)}{{[^}}]*}} ([0-9.e+]+)$", text, re.M))
    return out


def post(base: str, path: str, body: dict | None = None) -> None:
    request = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as response:
        response.read()


def round_of(base: str, model: str, prompt: str, streams: int, tokens: int) -> dict:
    results: list[dict] = []
    errors: list[str] = []

    def one() -> None:
        body = {"model": model, "prompt": prompt, "max_tokens": tokens, "temperature": 0,
                "ignore_eos": True}
        request = urllib.request.Request(base + "/v1/completions", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=1800) as response:
                results.append(json.loads(response.read()))
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            errors.append(repr(error))

    threads = [threading.Thread(target=one) for _ in range(streams)]
    start = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - start
    if errors:
        raise SystemExit("request failed: " + errors[0])
    text = sum(len(choice.get("text") or "") for body in results for choice in body.get("choices", []))
    return {"wall_s": wall, "completion_tokens": text, "requests": len(results)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("--streams", type=int, required=True)
    parser.add_argument("--tokens", type=int, default=256)
    parser.add_argument("--case", default="code", choices=sorted(PROMPTS))
    args = parser.parse_args()
    base = args.base.rstrip("/")
    with urllib.request.urlopen(base + "/v1/models", timeout=60) as response:
        model = json.load(response)["data"][0]["id"]
    prompt = PROMPTS[args.case]

    round_of(base, model, prompt, args.streams, 32)  # warm-up, not profiled

    control_before = counters(base)
    control = round_of(base, model, prompt, args.streams, args.tokens)
    control_after = counters(base)
    control_drafts = (control_after["vllm:spec_decode_num_drafts_total"]
                      - control_before["vllm:spec_decode_num_drafts_total"])
    control_steps = control_drafts / args.streams if args.streams else 0

    before = counters(base)
    post(base, "/start_profile")
    measured = round_of(base, model, prompt, args.streams, args.tokens)
    post(base, "/stop_profile")
    after = counters(base)

    drafts = after["vllm:spec_decode_num_drafts_total"] - before["vllm:spec_decode_num_drafts_total"]
    steps = drafts / args.streams if args.streams else 0
    print(json.dumps({
        "case": args.case, "streams": args.streams, "tokens": args.tokens,
        "wall_s": round(measured["wall_s"], 3),
        "completion_tokens": measured["completion_tokens"],
        "draft_events": drafts,
        "decode_steps": round(steps, 1),
        "step_ms": round(measured["wall_s"] * 1000 / steps, 3) if steps else None,
        "control_steps": round(control_steps, 1),
        "control_step_ms": round(control["wall_s"] * 1000 / control_steps, 3) if control_steps else None,
        "control_tokens_per_s": round(control["completion_tokens"] / control["wall_s"], 2),
        "tokens_per_s": round(measured["completion_tokens"] / measured["wall_s"], 2),
    }))


if __name__ == "__main__":
    main()
