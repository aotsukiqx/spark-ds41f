# Results: prefix-cache retention on spark-ds41f-1107 (2026-11-14)

Probe: one 62,962-token prefix, then (a) the same request eight times, (b) eight
different suffixes under the same prefix, (c) a pool-pressure phase. Numbers are
the API's `usage.prompt_tokens_details.cached_tokens` per request; the pressure
phase also reports the server's own `prefix_cache_hits/queries` counters.

## Reuse of one prefix

| Request | prompt tokens | cached | share |
| --- | ---: | ---: | ---: |
| first | 62,971 | 57,344 | 91.1% |
| second … eighth | 62,971 | **62,720** | **99.6%** |

62,720 = 245 × 256, the block-aligned prefix. **The 242-token tail is never
cached** — a consequence of the 256-token block size, not of the retention
policy: the first request caches whole blocks only, and every later request hits
all of them.

## Shared prefixes with different suffixes (agent traffic shape)

Eight different suffixes under the same 62,962-token prefix: **all eight cached
62,720 tokens** — a suffix does not disturb the shared prefix, and each request
pays prefill for its own tail only.

## Pool pressure

First attempt was invalid: the "200 distinct" prompts were built as the same
filler plus a suffix, so they *shared* the prefix and the pool never had to hold
independent entries (measured hit rate 99.61%, and the original prefix survived).

The corrected run gives each pressure prompt a unique leading identifier, so the
200 prompts are 200 unrelated 65K prefixes (~13M tokens against the 11M-token
pool). It was **stopped after 16 minutes, about two thirds of the way** — the
window's production downtime was the larger cost. What it did establish:

- the pressure was real: `prefix_cache_queries_total` rose 17.9M to 22.6M while
  `prefix_cache_hits_total` stayed at 13.68M, i.e. **zero cache hits across every
  pressure prompt** (they share nothing);
- the original 62,962-token prefix was still fully cached at the pre-pressure
  check (62,720 of its tokens), so nothing had evicted it before the pressure
  began.

**Unanswered:** whether the original prefix survives once unrelated prefixes
exceed the pool. That is the one #902 question this window did not settle; it
needs a run sized to fit the window (for example 170 × 65K = 11.05M tokens, the
pool's own size) or a longer window.

## Why this matters for the agent workload

Live traffic runs 64–100K prompts with 98–99% prefix-cache hits (TODO's 2026-09-28
window). The probe reproduces that at the block boundary: a long shared prefix
plus a short suffix is served from cache at 99.6%, and suffixes do not evict the
prefix. The open question is what happens when unrelated prefixes exceed the
pool, which is the corrected pressure run.
