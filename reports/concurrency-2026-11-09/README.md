# All-model API concurrency: tested overlap, not a hard ceiling

All seven model IDs returned by this Adaption account were tested together:
DeepSeek V4 Flash, both Gemma 4 endpoints, GLM 5.2, GLM 5.3 Flash,
Qwen 3.5 397B and Qwen 3.8 27B. See [metrics.json](metrics.json) for exact IDs,
settings, source hashes and aggregate measurements, and
[the design notes](../../docs/concurrency-testing.md) for methodology and scope.

## Results

- Both mixed-model waves with two copies of each model returned 14/14 valid
  replies, with 14 overlapping issued HTTP requests and two per model.
- The subsequent four-copy wave issued 28 overlapping requests, but returned
  one valid reply and 27 HTTP 429 responses. The probe stopped on rate limiting.
- Exactly 50 requests had succeeded across warmup and measured waves by that
  stop. The sequential ramp therefore confounds concurrency with accumulated
  requests in a potential shared rate window. It does **not** establish a
  two-per-model or 14-total concurrency ceiling.
- A separately labelled control waited at least 90 seconds after the first
  probe ended, then sent only one four-copy wave. **28/28 replies were valid**,
  all seven models overlapped, and each model reached four overlapping calls.
  This supports the rate-window explanation over an absolute 28-request
  concurrency failure, without identifying a documented quota or ruling out
  provider time variation. It is one control burst, not sustained-load evidence.

All requests asked for short synthetic JSON with a unique nonce. No shell or
agent tools were exposed. Validation was deterministic and strict. There were
no retries or per-model semaphores; connection capacity exceeded the requested
wave size. Intervals measure client-issued HTTP overlap, not provider GPU
execution. Completed and failed-request latency are both retained. Output
allowances were identical, but generated token lengths differ by model.

The first probe deliberately stopped escalating after the 429 wave; no load of
eight or sixteen copies per model was attempted. The cooldown control is not
pooled into the first probe's planned repetitions. Quota headers were not
captured in the original ramp; a later instrumentation change added an explicit
rate-header allowlist for the control and future tests. Other prompts, validation
and sampling settings were unchanged. The control used a new nonce trial ID.

Raw synthetic request records remain local under
`.village/concurrency-20261109T042453Z/`. This public-facing report contains
curated summaries only; the new code, notes and summaries are currently local.
Reported API costs include warmup and are not reconciled billing; transport
failures may incur unreported charges. Source files are hashed because the new
probe was run from a frozen copy before its code was committed.

## Consequence for the village

Our two-per-model cap was conservative rather than established by this test as
a provider limit. Before a faster population run, use representative agent
prompts, repeated spaced bursts and sustained trials, and distinguish account
request-rate pacing from concurrent-request limits. Mix/interleave the roster
in scheduling so all active workers are not drawn from the first model block.
Do not predict a 500-agent runtime directly from these short replies.

Capacity results do not establish behavioral generalisability. Replicate the
behavioral finding separately within model families, then compare matched
mixed-family villages, with independent whole-village repetitions. Keep a
family/task set held out from prompt tuning. The paused 500-agent run remains
paused; these probes did not change or resume it.
