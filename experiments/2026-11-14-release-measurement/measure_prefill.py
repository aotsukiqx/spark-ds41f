#!/usr/bin/env python3
"""Prefill measurement: cold first request, warm repeat, and one long-context prefill.

usage: measure_prefill.py BASE_URL [--target-tokens 500000] [--profile]

Every request streams, so the first content chunk's arrival is the prefill's
cost (time to first token) and ``prompt_tokens / ttft`` is the prefill rate. The
first request after a boot is measured cold, then repeated on the same prompt to
read the prefix cache's effect, then one long prompt built from repeated text.
With ``--profile`` the long prefill is wrapped in /start_profile .. /stop_profile.
"""
import argparse
import json
import time
import urllib.request

PROMPT = ("Write a complete Python implementation of an LRU cache using only the standard "
          "library. Include type hints, O(1) get and put methods, capacity validation, and a "
          "short executable example. Explain the complexity after the code.")
FILLER = ("The quick brown fox jumps over the lazy dog while the lighthouse keeper records the "
          "tide, the wind, and the state of every lamp for the morning report. ")


def post(base: str, path: str, body: dict, timeout: float = 3600) -> dict:
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=120) as response:
        return json.loads(response.read())


def tokenize(base: str, model: str, text: str) -> int:
    return int(post(base, "/tokenize", {"model": model, "prompt": text})["count"])


def stream(base: str, model: str, prompt: str, max_tokens: int) -> dict:
    body = json.dumps({"model": model, "prompt": prompt, "max_tokens": max_tokens,
                       "temperature": 0, "ignore_eos": True, "stream": True,
                       "stream_options": {"include_usage": True}}).encode()
    request = urllib.request.Request(base + "/v1/completions", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Accept": "text/event-stream"})
    start = time.perf_counter()
    ttft = None
    chunks = 0
    usage = {}
    with urllib.request.urlopen(request, timeout=3600) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices", []):
                if choice.get("text"):
                    chunks += 1
                    if ttft is None:
                        ttft = time.perf_counter() - start
    total = time.perf_counter() - start
    details = usage.get("prompt_tokens_details") or {}
    return {"ttft_s": round(ttft, 4) if ttft else None, "total_s": round(total, 3),
            "chunks": chunks, "prompt_tokens": usage.get("prompt_tokens"),
            "cached_tokens": details.get("cached_tokens"),
            "completion_tokens": usage.get("completion_tokens")}


def report(base: str, model: str, prompt: str, limit: int, label: str,
           profile: bool = False, tokens: int | None = None) -> dict:
    if profile:
        post(base, "/start_profile", {}, timeout=120)
    row = stream(base, model, prompt, limit)
    if profile:
        post(base, "/stop_profile", {}, timeout=600)
    prompt_tokens = tokens if tokens is not None else row["prompt_tokens"]
    row.update({"label": label, "prompt_tokens": prompt_tokens,
                "prefill_tokens_per_s": (round(prompt_tokens / row["ttft_s"], 1)
                                         if prompt_tokens and row["ttft_s"] else None)})
    print(json.dumps(row), flush=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("--target-tokens", type=int, default=500_000)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    model = get(base, "/v1/models")["data"][0]["id"]

    report(base, model, PROMPT, 8, "cold-first-request")
    report(base, model, PROMPT, 8, "warm-repeat")
    unit_tokens = tokenize(base, model, FILLER)
    text = FILLER * max(1, args.target_tokens // unit_tokens)
    tokens = tokenize(base, model, text)
    report(base, model, text, 4, "long-prefill", profile=args.profile, tokens=tokens)


if __name__ == "__main__":
    main()
