# Capacity, model diversity, and incident relevance

**First measurements:** [all-model mixed bursts and cooldown control](../reports/concurrency-2026-11-09/README.md).
The cooldown control supports 28 overlapping HTTP requests across all seven
models. The initial fast ramp hit 429s after 50 accepted requests; it cannot
isolate concurrent-load limits from cumulative request-rate limits. Space future
waves according to quota/reset information before escalating, and include
representative prompts before applying the result to village scheduling.

## What we are trying to learn

The [METR investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/)
describes an incident involving a population dominated by one research model,
with a smaller contribution from another model. Agents discovered a shared
communication channel, coordinated around difficult/impossible tasks, and
treated peer messages as consequential instructions. It does not establish
that a diverse model roster caused the behavior. Our mock task and provided
board capture only a small part of that setting, not the incident as a whole.

Model diversity belongs in the research design, but three questions differ:

1. **Replication across models:** does a behavioral finding hold in homogeneous
   groups from multiple independent model families?
2. **Composition effect:** with population size, tasks, tools, turn allowance
   and scheduling held fixed, does a mixed-model group behave differently?
3. **Provider capacity:** how many simultaneous inference requests work for
   one model and for the entire account? This is operational calibration.

A simultaneous all-model API load test answers question 3. It cannot establish
questions 1 or 2. Likewise, using several Qwen endpoints is not equivalent to
replication across several independently developed model families.

[Zhang et al. (2025)](https://arxiv.org/abs/2502.08788) find advantages from
heterogeneity in their debate experiments, while also criticizing weak
baselines. [Ganesh et al. (2026)](https://arxiv.org/abs/2610.09824) find that
mixed models do not by themselves prevent homogenization and correlated
failures. These results concern their respective tasks; neither establishes
that diversity will help our village. We should measure that effect.

## Small engineering verification loop

Following the benchmarking concepts in the official
[vLLM serving benchmark](https://docs.vllm.ai/en/latest/cli/bench/serve/) and
[GuideLLM metrics guide](https://vllm-project.github.io/guidellm/stable/guides/metrics/):

1. Test the measurement machinery offline with a fake provider that requires
   multiple requests from every model to be in flight before replying. Also
   test failed responses and non-overlapping timestamps.
2. Pause unrelated experiment traffic. Discover the account's current catalogue
   rather than guessing supported model IDs. Record the source and settings.
3. Warm up all models together, retaining warmup outcomes separately.
4. Probe ascending mixed-model waves: **1, 2, 4, 8, 16 copies of every model**, two
   waves per level. All models start together at every level. This is a finite
   synchronized-burst probe, not a steady-state saturation benchmark.
5. Record issued HTTP intervals, actual overlap globally/per model, status
   codes, strict output validity, truncation, all-outcome p50/p95 latency,
   valid replies/sec and reported usage. Failed requests stay in denominators.
6. Stop escalating on rate limiting, poor validity, authentication failure,
   unknown cost, or budget exhaustion. Inspect the cause before another test.
7. Confirm any promising setting with longer, representative agent prompts
   and repeated sustained-load trials. Then compare isolated model runs with
   mixed-model runs to distinguish endpoint from account-level contention.

The first probe uses synthetic short JSON replies with unique nonces, a
2048-token output allowance, temperature zero, a 90-second HTTP timeout and no
automatic retries or per-model semaphore. The HTTP connection pool is sized
for the largest requested wave so its default capacity cannot silently cap
the experiment. Only exact, completed JSON replies count as valid; a partial
generation is recorded as truncated even if its JSON happens to parse.

Default cap: **$0.25 soft budget**. In-flight requests may overshoot it, and
transport failures can incur unreported charges. The reported cost is not a
reconciled bill. A rung stops escalation if any measured wave has a 429 or any
model returns fewer than 75% valid replies. This is an exploratory operational
gate, not a statistically established reliability threshold. No failing model
is silently removed from the catalogue to improve the aggregate result.

Warmup is excluded from measured wave rates. No retries hide first-attempt
failure. Latency includes failed issued requests, not only fast successes.
Output token counts must be inspected before comparing throughput: identical
allowances do not imply identical generated lengths. There is no streaming or
time-to-first-token measurement. Client HTTP overlap does not prove parallel
GPU execution inside the provider. A successful burst is a tested operating
point, not a universal hard ceiling or a predicted 500-agent completion time.

```bash
python -m pytest -q
python scripts/probe_concurrency.py --output .village/concurrency-new
# A separately labelled isolated follow-up, not pooled with mixed waves:
python scripts/probe_concurrency.py --models deepseek-v4-flash \
  --output .village/concurrency-isolated-new
```

Exact per-request synthetic data and progress are written to `report.json`
after each wave. Headers, credentials, provider error bodies and exception
text are excluded. No model-generated commands or external actions are run.

## Behavioral research after capacity calibration

Start small enough to repeat the experiment, rather than treating one large
run as many independent replications. A useful next design is homogeneous
DeepSeek, Qwen and GLM groups plus a balanced mixture of those groups, each
crossed with board enabled/disabled. Keep population size, per-agent turn caps,
tasks, sampling settings and eligible tools fixed. Randomize task assignments
and interleave model identities in the scheduler; do not queue all DeepSeek
agents before every other family, as the old weighted roster currently does.

Repeat whole villages with independent task seeds; agents within a village
are dependent observations. Report actual completed turns, tokens, spend,
latency and errors for every condition. Equal turn allowances are not equal
token or dollar budgets; report rather than conceal those differences. Use
grounded task outcomes and actual consequential peer influence, not message
volume or heuristic coalition labels alone, as the primary evidence.

Reserve a model family and task variants for a held-out replication after
freezing prompts and metrics. Even a successful replication across these
models supports only a bounded claim about the tested environments. The real
incident also involved different training, capabilities, exposure, task
pressure and timescales. Neither mixed models nor high concurrency bridges
those gaps by itself.

## Pausing the existing run

The current process is suspended with SIGSTOP, preserving its Python threads,
queue and memory. A runtime-only systemd override suspends its shutdown deadline.
Docker workspaces are retained. Resumption uses the prepared local helper to
restore a deadline four hours from resumption and send SIGCONT to the same PID.
This does not survive reboot. In-flight HTTP requests, subprocess waits and
per-agent monotonic deadlines may expire during the pause; some currently
active agents may therefore retry or terminate after resumption. Preserve that
pause event in the analysis and do not call this an uninterrupted baseline.
