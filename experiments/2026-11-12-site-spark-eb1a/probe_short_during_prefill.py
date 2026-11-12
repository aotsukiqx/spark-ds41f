#!/usr/bin/env python3
"""A short request arriving while one cold 700 Ki prefill runs.

Starts a 700,000-token cold prompt (unique cache salt), then sends short chat requests at
fixed offsets during its prefill. Reports the long prefill's first token and each short
request's time to first token, which is what a mixed agent workload feels.

usage: probe_short_during_prefill.py [--url ...] [--tokens 700000] [--offsets 20,50,80]
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request
import uuid

FILLER_WORDS = (
    "system", "model", "token", "layer", "matrix", "kernel", "stream", "cache", "block",
    "queue", "shard", "tensor", "batch", "prefix", "decode", "prefill", "graph", "rank",
)


def filler(tokens: int, seed: int) -> str:
    body = " ".join(FILLER_WORDS[(i * 7 + seed) % len(FILLER_WORDS)] for i in range(tokens))
    return f"Document {seed}:\n{body}\n\nSummarize the document above in one sentence."


def post(url: str, path: str, payload: dict, timeout: float = 3600) -> urllib.request.Request:
    return urllib.request.Request(
        f"{url}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )


def token_count(url: str, model: str, prompt: str) -> int | None:
    try:
        with urllib.request.urlopen(post(url, "/tokenize", {
                "model": model, "prompt": prompt, "add_special_tokens": False}), timeout=120) as r:
            return int(json.loads(r.read())["count"])
    except (OSError, ValueError, KeyError):
        return None


def calibrate(url: str, model: str, tokens: int, seed: int) -> tuple[str, int | None]:
    words, prompt = tokens, filler(tokens, seed)
    count = token_count(url, model, prompt)
    while count and count > tokens:
        words = max(1, int(words * tokens / count) - 1)
        prompt = filler(words, seed)
        count = token_count(url, model, prompt)
    return prompt, count


def long_prefill(url: str, model: str, prompt: str, results: dict) -> None:
    # A chat request with thinking off streams its first token; a four-token completion can
    # spend every token on reasoning and never emit text, leaving no first-token sample.
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt + "\n\nSummarize the document above in one sentence."}],
        "max_tokens": 16, "temperature": 0, "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"thinking": False},
        "cache_salt": uuid.uuid4().hex,
    }
    started = time.monotonic()
    try:
        with urllib.request.urlopen(post(url, "/v1/chat/completions", payload), timeout=3600) as response:
            for raw in response:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                event = json.loads(body)
                # The first token of any kind is the first token: content, reasoning or
                # reasoning_content, whichever the model streams first.
                if any(
                    (choice.get("text") or (choice.get("delta") or {}).get("content")
                     or (choice.get("delta") or {}).get("reasoning")
                     or (choice.get("delta") or {}).get("reasoning_content"))
                    for choice in event.get("choices", [])
                ):
                    results["long_ttft_s"] = round(time.monotonic() - started, 2)
                    usage = event.get("usage") or {}
                    if usage.get("prompt_tokens"):
                        results["long_prompt_tokens"] = usage["prompt_tokens"]
                    break
    except Exception as error:  # noqa: BLE001
        results["long_error"] = f"{type(error).__name__}: {error}"
    results["long_started"] = round(started, 3)


def short_probe(url: str, model: str, label: str, out: list) -> None:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "In one sentence, what does a KV cache store?"}],
        "max_tokens": 64, "temperature": 0, "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"thinking": False},
        "cache_salt": uuid.uuid4().hex,
    }
    started = time.monotonic()
    record = {"label": label}
    try:
        with urllib.request.urlopen(post(url, "/v1/chat/completions", payload), timeout=1800) as response:
            for raw in response:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                event = json.loads(body)
                if any((choice.get("delta") or {}).get("content") for choice in event.get("choices", [])):
                    record["ttft_s"] = round(time.monotonic() - started, 2)
                    break
    except Exception as error:  # noqa: BLE001
        record["error"] = f"{type(error).__name__}: {error}"
    out.append(record)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="deepseek-v4.1-flash")
    parser.add_argument("--tokens", type=int, default=700_000)
    parser.add_argument("--offsets", default="20,50,80")
    parser.add_argument("--seed", type=int, default=99)
    args = parser.parse_args()
    offsets = [float(value) for value in args.offsets.split(",") if value.strip()]

    prompt, count = calibrate(args.url, args.model, args.tokens, args.seed)
    results: dict = {}
    short: list = []
    long_thread = threading.Thread(target=long_prefill, args=(args.url, args.model, prompt, results))
    long_thread.start()
    began = time.monotonic()
    for offset in offsets:
        while time.monotonic() - began < offset:
            time.sleep(0.2)
        short_probe(args.url, args.model, f"t+{offset:g}s", short)
    long_thread.join()
    print(json.dumps({
        "calibrated_prompt_tokens": count,
        "short_requests": short,
        "long": results,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
