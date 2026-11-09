# Fresh paced population run — 2026-11-09

## Final decision: six turns with faster scheduling

At approximately 08:43 UTC the user chose to restore the six-turn allowance,
then explicitly considered changing concurrency for time reasons. The final
run uses the six-turn frozen plan below, 500 agents, 28 rolling active loops,
1.6-second HTTP spacing, original weighted roster shuffled with seed 20261109,
8,192 output tokens, two HTTP attempts, 1,800-second per-agent allowance,
$10 shared soft cap, and a 150-minute main cutoff. The successful 28-agent
operational canary is reused. Its partial three-turn predecessor is retained:
47 end records, 75 starts, 159 returned turns and 168 HTTP attempts were
observed before stopping it; these are not pooled with the final run.

This is an exploratory follow-up under a different execution policy, **not an
exact replication of Ajit's run and not a controlled estimate of concurrency's
effect**. Agent count and turn allowance match, but scheduling, pacing, roster
order, output allowance and retry policy differ. Ajit's exact execution source
revision and complete effective config were not present in the public dataset.
Interpret any recurrence of controller-confirmed target modification
descriptively; absence is not evidence of equivalence or safety.

Before this final run, the runner's metrics were corrected so overlapping chat
calls do not double-count the shared client's retry/truncation counters. This
changes instrumentation, not prompts or model sampling. Dispatch logs remain
the audit trail for the actual HTTP attempts. Later code changes do not affect
the frozen execution snapshot. Do not change settings in response to outcomes.

The amendments below preserve the decisions for the interrupted attempts.

## User-requested speed amendment

After the 28-agent canary passed operational readiness (28/28 returned, zero
model-call errors, no sandbox loss; valid-turn yield 89.3%), the six-turn
500-agent run began at 08:27 UTC. The user immediately requested a faster run.
Only that new run was interrupted; its partial evidence is retained separately.
The original earlier SIGSTOP-paused process remains unchanged.

The replacement keeps 500 agents, the shuffled four-model roster, 28 rolling
active loops, 1.6-second HTTP spacing and the 8,192-token output allowance,
but caps each agent at **three action turns**. At most 1,500 action calls means
approximately 40 minutes of paced dispatch before retries/setup/tail. Target
45–60 minutes, with a 90-minute main cutoff. The successful canary is reused,
not rerun. This is a shorter behavioral window and is not comparable to a
completed six-turn study. A completed process must still report malformed
actions and cannot establish useful cooperation. The remaining frozen-plan
text below describes the superseded six-turn attempt for provenance.

The user authorised a separate faster 500-agent run because the original
SIGSTOP-paused run would likely need approximately six additional hours at
its old settings. The old process and its containers remain untouched.

This is a descriptive operational/population experiment, not the gated
communication-effect study. That study remains unlaunched after calibration
failure. This run cannot establish a causal communication effect or broad
model-family generalisation. Invalid actions, sandbox loss and provider errors
must be reported even if the process returns normally. Six attempted action
turns is a cap, not a promise of six useful actions per agent.

## Frozen plan

- Local network-disabled Docker; `mock:impossible`; no real CyberGym targets.
- 500 agents, up to 28 rolling active loops, six action turns each.
- Original weighted four-model roster: DeepSeek flash 60%, GLM flash 20%,
  Qwen 27B 15%, Qwen 397B 5%. Deterministic roster shuffle seed 20261109
  interleaves model families instead of beginning with a long single-model block.
- Shared board and existing population prompts; no seeded false claims or
  changes to the task to induce a desired result.
- Shared HTTP-attempt spacing 1.6 seconds, including every retry. This is
  approximately 37.5 attempts/minute, not a claim about the provider's quota.
- No additional per-model semaphore; request timeout 120 seconds, at most two
  HTTP attempts per call. Action output allowance 8,192 tokens; temperature
  and normal tool policy retain the population runner's defaults.
- Per-agent wall allowance 1,800 seconds; shared USD soft cap $10. In-flight
  calls can overshoot the cap; this is provider-reported usage, not reconciled billing.
- Short 28-agent, one-turn canary first, excluded from the main run. Launch
  only if its process returns, all 28 agent end records exist, and its model-call
  error fraction is at most 10%. This checks operational readiness, not action
  validity or the outcome. No tuning based on primary behaviors.
- Main wall cutoff 150 minutes after launch; enclosing service 160 minutes,
  including canary/setup/cleanup. A cutoff is reported as incomplete, not as
  a completed 500-agent study. The user must be informed if the canary fails.

At 3,000 action calls, pacing alone takes about 80 minutes before retries,
setup and tail latency. The target is roughly 90–120 minutes; completion is
not guaranteed. No other paid run or capacity probe should contend for the
same provider account during this run.

## Measurement and preservation

Freeze the code at a committed Git revision, record execution metadata and
effective settings before inference, and log model/monotonic dispatch time
for every HTTP attempt without headers or prompt contents. Source modifications
after launch cannot alter the frozen run. Current `peak`/latency counters measure
chat invocations including scheduler/pacing waits, not simultaneous backend
execution. Social-analyser coalitions are heuristics, not established cooperation.

Keep all per-agent logs and partial outcomes. Publish new evidence separately
from both Ajit's `scale-500-20261109T024735` run and our original paused
`scale-500-20261109T035401` run. Cleanup selects only containers mounted below
the fresh run's frozen source directory. It must never remove the old run's
containers or change its service runtime override.
