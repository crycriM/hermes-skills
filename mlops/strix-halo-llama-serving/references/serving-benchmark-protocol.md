# Benchmarking a locally served LLM (Strix Halo, one user)

How to produce prefill/decode numbers that mean something, on this box or any
single-user host with a big model behind an OpenAI-compatible endpoint. Written
after a session where three of the five traps below each cost a re-run.

## Take the numbers from the server, never from the wall clock

- Decode rate = `timings.predicted_per_second`, prefill rate =
  `timings.prompt_per_second` (llama.cpp's field names; forks and dedicated
  engines copy them). `timings.prompt_ms` / `predicted_ms` give the split.
- **Never compute decode as `completion_tokens / wall_seconds`.** Wall includes
  prefill, and at long context prefill is nearly all of it: one measured
  request spent 44.2 s of a 46.5 s wall in prefill to generate 128 tokens, so
  the wall-clock figure read 2.8 tok/s against a true 56.7.
- `timings` also carries the diagnostics that explain a number you do not
  believe: `cache_n` (the request was answered from the prompt cache),
  `draft_n` / `draft_n_accepted` (speculation acceptance, i.e. tokens committed
  per round), `prefix_n`, `disk_restore_n`.
- Report decode per prompt shape AND as a mean with the shape set named. At one
  depth the spread was 34-63 tok/s, entirely draft acceptance (code and proof
  draft well, chat and prose badly). A single prose prompt understates such an
  engine by ~30%.

## Build prompts of a known length without loading a tokenizer

Calibrate against the server itself: one `max_tokens=1` request for the
fixed template overhead, one with N filler units for tokens-per-unit, then size
the text. Two probes, no `transformers` in the bench process, and the template's
overhead is measured rather than assumed (13 tokens overhead / 18 tokens per
filler unit for the Qwen chat template plus a repeated filler sentence).

Repeat one filler sentence: prefill cost is matmul FLOPs over the token count,
not the content, and a repeated sentence makes the length predictable.

**Give every request a unique prefix** (a short distinct marker at the very
front). A server with prefix caching will otherwise answer a repeat from its
cache and report a prefill rate that read nothing. The nastiest version is a
size sweep that reuses one filler text: each longer length is a *prefix* of the
next, so `pp32768` warms `pp65536` and the sweep prints 2,841 tok/s for a
64k prompt whose honest cold rate is ~1,490.

## Protocol

1. **Warm up, discard the row.** One request at the target depth, ~64 tokens,
   before measuring anything. If any of the model is paged rather than
   resident, the first request pays it: one engine read a 16-rows-per-token
   lookup table from disk on its first request and decoded at 28-32 tok/s where
   steady state was 40-62, with *identical* draft acceptance. An A/B arm run
   without a warmup measures the disk.
2. Per depth, per shape, R reps, greedy (`temperature 0`), thinking off.
3. A request reserves `prompt + max_tokens` against the server's context
   limit, so a depth probe must clamp its prompt target to
   `ctx - max_tokens - margin`; asking past it is a hard 400, not a truncation.
4. For a config A/B: one restart per arm, tag every row with the arm name, keep
   one discarded warmup per arm, and **verify the knob took effect from the
   server's own startup line or `/health`, never from the fact that you passed
   it** — a capped or ignored flag looks exactly like a knob that did nothing.
5. Print which row was first in each arm, or the warmup leaks into the mean.

## Comparing against another engine or recipe

- Same prompts, same depths, same generation length, same sampling, same
  thinking setting. A harness that sends an engine-specific thinking flag to an
  engine that ignores it silently compares thinking-on against thinking-off.
- **Reproduce the other engine's published table on your box first.** If its
  published 32k figure is 103.7 s and you measure 90.0 s, the gap to your
  favourite is the engines, not a badly-tuned arm; if you measure 3x worse, your
  flags are wrong and the comparison is worthless.
- State the precision difference (bits per weight, KV dtype). Different quants
  compare recipes, not engines.
- Two engines that each want most of the machine cannot be measured side by
  side: stop one, let its page cache drain, then start the other. A lane started
  immediately into a box that just released ~68 GB of weights can fail where the
  same lane started into an idle box succeeds.

## Traps that read as something else

- `503` on `/health` while loading (and again when all slots are busy). Gate on
  the body's `"status":"ok"`; `curl -s >/dev/null` and `urlopen` both treat the
  503 response as success, so a readiness loop reports "ready after 2s" and
  every measurement then dies on the first request. Retry 503 in any client.
- A connection reset on a long prompt is the server dying (check host memory and
  GPU memory accounting), not a client bug.
- Low RSS is not a failed load for a model served with `mmap` + lazy tensor
  reads: a 95 GB model legitimately holds a few GB resident.
