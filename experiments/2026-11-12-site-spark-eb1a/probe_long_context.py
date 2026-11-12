#!/usr/bin/env python3
"""N concurrent full-length requests: admission, first token, and decode at long context.

Sends ``--requests`` requests, each a distinct filler document of ``--tokens`` tokens
(distinct seeds, so no prefix-cache block is shared), forces ``--output-tokens`` of
generation, and streams every response. Prints one JSON summary: per-request prompt and
output tokens, time to first token, per-stream decode tokens/s, the aggregate, and the
server's running/waiting/kv counters sampled throughout.

usage: probe_long_context.py [--url http://127.0.0.1:8000] [--requests 10] [--tokens 700000]
                            [--output-tokens 256] [--timeout 3600]
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
    """About one token per word, as bench.filler: the seed rotates the vocabulary so two
    documents share no opening tokens (no prefix-cache block) and differ throughout."""
    body = " ".join(FILLER_WORDS[(i * 7 + seed) % len(FILLER_WORDS)] for i in range(tokens))
    return f"Document {seed}:\n{body}\n\nSummarize the document above in one sentence."


def metrics(url: str) -> dict[str, float]:
    try:
        text = urllib.request.urlopen(f"{url}/metrics", timeout=5).read().decode()
    except OSError:
        return {}
    totals: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        head = line[:line.index("{")] if "{" in line else line.split(" ")[0]
        rest = line[line.rindex("}") + 1:] if "{" in line else line[len(head):]
        try:
            value = float(rest.strip().split(" ")[0])
        except (ValueError, IndexError):
            continue
        if value == value:
            totals[head] = totals.get(head, 0.0) + value
    return totals


def stream_one(url: str, model: str, prompt: str, output_tokens: int, barrier: threading.Barrier,
               results: list, index: int, salt: str) -> None:
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": output_tokens,
        "min_tokens": output_tokens,
        "ignore_eos": True,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        # A stable salt keeps one probe's requests apart from another's while a repeat of
        # the same probe reuses the prefix cache it filled; empty leaves it random (cold).
        "cache_salt": salt or uuid.uuid4().hex,
    }
    request = urllib.request.Request(
        f"{url}/v1/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    record: dict = {"request": index, "ok": False}
    started = first = last = 0.0
    tokens = 0
    try:
        barrier.wait(timeout=60)
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=3600) as response:
            for raw in response:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                event = json.loads(body)
                now = time.monotonic()
                for choice in event.get("choices", []):
                    text = choice.get("text") or ""
                    if not text:
                        continue
                    if not first:
                        first = now
                    tokens += 1
                    last = now
                usage = event.get("usage")
                if usage:
                    record["prompt_tokens"] = usage.get("prompt_tokens")
                    record["reported_output_tokens"] = usage.get("completion_tokens")
        finished = time.monotonic()
        # One delta can carry several tokens (DSpark and CopyDrafter group them), so the
        # stream's own usage block is the authoritative count; the delta count is kept for
        # first-token timing only.
        generated = record.get("reported_output_tokens") or tokens
        record.update(
            ok=True,
            tokens=tokens,
            completion_tokens=generated,
            ttft_s=round(first - started, 3) if first else None,
            decode_s=round(finished - first, 3) if first else None,
            decode_tps=round((generated - 1) / (last - first), 3) if first and last > first else None,
            wall_s=round(finished - started, 3),
        )
    except Exception as error:  # noqa: BLE001 - one request's failure is data, not a crash
        record["error"] = f"{type(error).__name__}: {error}"
    results[index] = record


def token_count(url: str, model: str, prompt: str) -> int | None:
    """The server's own count for a prompt, or None when /tokenize is unavailable."""
    request = urllib.request.Request(
        f"{url}/tokenize",
        data=json.dumps({"model": model, "prompt": prompt, "add_special_tokens": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return int(json.loads(response.read())["count"])
    except (OSError, ValueError, KeyError):
        return None


def calibrate(url: str, model: str, tokens: int, seed: int) -> tuple[str, int | None]:
    """A filler prompt whose token count is at most ``tokens`` and within 1% of it.

    The filler averages about one token a word; one round of the server's own count sizes
    the request the probe claims instead of an estimate of it.
    """
    words = tokens
    prompt = filler(words, seed)
    count = token_count(url, model, prompt)
    while count and count > tokens:
        words = max(1, int(words * tokens / count) - 1)
        prompt = filler(words, seed)
        count = token_count(url, model, prompt)
    return prompt, count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="deepseek-v4.1-flash")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--tokens", type=int, default=700_000)
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--salt-prefix", default="",
                        help="a stable cache-salt prefix (salt = PREFIX-INDEX); a repeat of the "
                             "same probe then reuses the prefix cache the first run filled. "
                             "Empty keeps every request cold.")
    args = parser.parse_args()

    prompts, calibrated = [], []
    for seed in range(args.requests):
        prompt, count = calibrate(args.url, args.model, args.tokens, seed + 1)
        prompts.append(prompt)
        calibrated.append(count)
    results: list = [None] * args.requests
    barrier = threading.Barrier(args.requests)
    threads = [
        threading.Thread(target=stream_one, args=(
            args.url, args.model, prompts[index], args.output_tokens, barrier, results, index,
            f"{args.salt_prefix}-{index}" if args.salt_prefix else ""))
        for index in range(args.requests)
    ]
    samples: list[dict] = []
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            values = metrics(args.url)
            samples.append({
                "t": round(time.monotonic(), 1),
                "running": values.get("vllm:num_requests_running"),
                "waiting": values.get("vllm:num_requests_waiting"),
                "kv": values.get("vllm:kv_cache_usage_perc") or values.get("vllm:gpu_cache_usage_perc"),
                "preemptions": values.get("vllm:num_preemptions_total"),
            })
            stop.wait(5.0)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stop.set()
    wall = time.monotonic() - started
    sampler.join(timeout=10)

    ok = [record for record in results if record and record.get("ok")]
    summary = {
        "requests": args.requests,
        "requested_prompt_tokens": args.tokens,
        "calibrated_prompt_tokens": calibrated,
        "requested_output_tokens": args.output_tokens,
        "wall_s": round(wall, 1),
        "ok": len(ok),
        "prompt_tokens": sorted({record.get("prompt_tokens") for record in ok if record.get("prompt_tokens")}),
        "error_count": len([record for record in results if record and not record.get("ok")]),
        "ttft_s": sorted(record["ttft_s"] for record in ok if record.get("ttft_s")),
        "decode_tps": sorted(record["decode_tps"] for record in ok if record.get("decode_tps")),
        "aggregate_decode_tps": round(sum(record["decode_tps"] for record in ok if record.get("decode_tps")), 1),
        "peak_running": max((sample["running"] or 0 for sample in samples), default=None),
        "peak_kv": max((sample["kv"] or 0 for sample in samples), default=None),
        "preemptions": max((sample["preemptions"] or 0 for sample in samples), default=None),
        "samples": len(samples),
        "results": results,
    }
    print(json.dumps(summary, indent=1))
    return 0 if len(ok) == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
